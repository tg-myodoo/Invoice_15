import json
import logging
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tools import get_lang, float_compare, format_date, formatLang, ormcache

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    correction_invoices_ids = fields.One2many('account.move', 'refund_invoice_id')
    correction_invoices_len = fields.Integer(compute='_x_compute_correction_invoices_len', store=False)
    refund_invoice_id = fields.Many2one('account.move')

    original_invoice_line_ids = fields.Many2many(
        comodel_name='account.move.line',
        string='Original Invoice Lines',
        compute='_x_compute_original_invoice_line_ids',
        readonly=True,
        store=False,
        tracking=False,
    )

    corrected_invoice_line_ids = fields.One2many(
        'account.move.line',
        'move_id',
        string='Corrected Invoice lines',
        copy=False,
        readonly=True,
        compute='_x_compute_corrected_invoice_line_ids',
        inverse='_x_inverse_corrected_invoice_line_ids',
        states={'draft': [('readonly', False)]},
    )

    x_corrected_amount_by_group = fields.Binary(
        string='Corrected Tax amount by group', readonly=True, compute='_x_compute_invoice_taxes_by_group'
    )
    x_corrected_amount_summary = fields.Binary(
        string='Corrected Tax amount summary', readonly=True, compute='_x_compute_invoice_taxes_by_group'
    )

    selected_correction_invoice = fields.Many2one('account.move')

    x_invoice_sale_date = fields.Date(string='Sale/Currency Date')
    x_invoice_duplicate_date = fields.Date(string='Duplicate Date', copy=False)
    # x_invoice_amount_summary = fields.Binary(string='Tax amount summary', compute='_compute_invoice_taxes_by_group')

    # connected sale order (for advance invoice pdf)
    advance_source_id = fields.Many2one('sale.order', compute='compute_advance_source_id', store=False)
    # connected final invoice (for advance invoice pdf)
    final_invoice_ids = fields.Many2many('account.move', compute='compute_advance_source_id', store=False)
    # connected sale order (for final invoice pdf)
    final_source_id = fields.Many2one('sale.order', compute='compute_advance_invoices_ids', store=False)
    # connected advance invoices (for final invoice pdf)
    advance_invoices_ids = fields.Many2many('account.move', compute='compute_advance_invoices_ids', store=False)

    is_downpayment = fields.Boolean()
    x_is_poland = fields.Boolean(compute='_x_compute_is_poland', string='Technical Field: Is Poland')
    x_invoice_sign = fields.Integer(compute='x_compute_invoice_sign')
    x_corrected_amount_total = fields.Float(compute='_x_compute_corrected_amount_total')

    x_amount_total = fields.Monetary(string='X Total in Currency', compute='_x_compute_amount')
    x_amount_residual = fields.Monetary(string='X Amount Due', compute='_x_compute_amount')
    x_currency_rate = fields.Float('Currency Rate', digits=(16, 4))
    x_show_currency_rate = fields.Boolean(compute='_x_compute_show_currency_rate')

    @api.model
    @ormcache('self')
    def x_get_is_poland(self):
        """normally x_is_poland should be used, but for the record sets, this method should be used"""
        return self.env.company.country_id.id == self.env.ref('base.pl').id

    def _x_compute_is_poland(self):
        for rec in self:
            rec.x_is_poland = rec.x_get_is_poland()

    def get_final_invoice_summary(self, with_downpayments=True):
        self.ensure_one()

        if not self.is_invoice(include_receipts=True):
            return None

        tax_totals = self._get_tax_totals(
            self.partner_id,
            self._prepare_tax_lines_data_for_totals_from_invoice(),
            self.amount_total,
            self.amount_untaxed,
            self.currency_id,
        )

        if with_downpayments or not self.advance_invoices_ids:
            return tax_totals

        for advance_invoice_id in self.advance_invoices_ids:
            advance_tax_totals = advance_invoice_id._get_tax_totals(
                advance_invoice_id.partner_id,
                advance_invoice_id._prepare_tax_lines_data_for_totals_from_invoice(),
                advance_invoice_id.amount_total,
                advance_invoice_id.amount_untaxed,
                advance_invoice_id.currency_id,
            )

            # merge structures group_by_subtotal
            for a_group_name, a_group in advance_tax_totals['groups_by_subtotal'].items():
                for group_name, group in tax_totals['groups_by_subtotal'].items():
                    if group_name == a_group_name:
                        for a_tax_group in a_group:
                            for tax_group in group:
                                if a_tax_group['tax_group_id'] == tax_group['tax_group_id']:
                                    # add values
                                    for key in (
                                        'tax_group_amount',
                                        'tax_group_base_amount',
                                        'x_tax_group_total_amount',
                                        'x_tax_group_amount_in_pln',
                                    ):
                                        tax_group[key] += a_tax_group[key]

                                    # update formatted values
                                    tax_group['formatted_tax_group_amount'] = formatLang(
                                        self.env, tax_group['tax_group_amount'], currency_obj=self.currency_id
                                    )
                                    tax_group['formatted_tax_group_base_amount'] = formatLang(
                                        self.env, tax_group['tax_group_base_amount'], currency_obj=self.currency_id
                                    )
                                    tax_group['x_formatted_tax_group_total_amount'] = formatLang(
                                        self.env, tax_group['x_tax_group_total_amount'], currency_obj=self.currency_id
                                    )
                                    tax_group['x_formatted_tax_group_amount_in_pln'] = formatLang(
                                        self.env,
                                        tax_group['x_tax_group_amount_in_pln'],
                                        currency_obj=self.env.company.currency_id,
                                    )

                                    break
                            else:
                                # no matching tax group found, adding one
                                group.append(a_tax_group)

                        break
                else:
                    # no match found, append group from advance invoice
                    tax_totals['group_by_subtotal'][a_group_name] = a_group

            # mege structure of subtotals
            for a_group in advance_tax_totals['subtotals']:
                for group in tax_totals['subtotals']:
                    if a_group['name'] == group['name']:
                        group['amount'] += a_group['amount']
                        group['formatted_amount'] = formatLang(self.env, group['amount'], currency_obj=self.currency_id)
                        break
                else:
                    # no matching subtotal found
                    tax_totals['subtotals'].append(a_group)

            # update totals
            tax_totals['amount_total'] += advance_tax_totals['amount_total']
            tax_totals['amount_untaxed'] += advance_tax_totals['amount_untaxed']
            tax_totals['x_tax_amount'] += advance_tax_totals['x_tax_amount']
            tax_totals['x_tax_amount_in_pln'] += advance_tax_totals['x_tax_amount_in_pln']

            tax_totals['formatted_amount_total'] = formatLang(
                self.env, tax_totals['amount_total'], currency_obj=self.currency_id
            )
            tax_totals['formatted_amount_untaxed'] = formatLang(
                self.env, tax_totals['amount_untaxed'], currency_obj=self.currency_id
            )
            tax_totals['x_formatted_tax_amount'] = formatLang(
                self.env, tax_totals['x_tax_amount'], currency_obj=self.currency_id
            )
            tax_totals['x_formatted_tax_amount_in_pln'] = formatLang(
                self.env, tax_totals['x_tax_amount_in_pln'], currency_obj=self.env.company.currency_id
            )

        # return json.dumps(tax_totals)
        return tax_totals

    def _prepare_tax_lines_data_for_totals_from_invoice(self, tax_line_id_filter=None, tax_ids_filter=None):
        # self.ensure_one() not needed - tested in super()
        result = super()._prepare_tax_lines_data_for_totals_from_invoice(tax_line_id_filter, tax_ids_filter)

        if not self.x_get_is_poland():
            return result

        tax_line_id_filter = tax_line_id_filter or (lambda aml, tax: True)
        tax_ids_filter = tax_ids_filter or (lambda aml, tax: True)

        balance_multiplier = -1 if self.is_inbound() else 1
        tax_lines_data = []

        for line in self.line_ids:
            if line.tax_line_id and tax_line_id_filter(line, line.tax_line_id):
                tax_lines_data.append(
                    {
                        'line_key': 'tax_line_%s' % line.id,
                        'tax_amount': line.amount_currency * balance_multiplier,
                        'tax': line.tax_line_id,
                        'x_balance': line.balance * balance_multiplier,
                        'x_invoice_sign': line.move_id.x_get_invoice_sign(),
                    }
                )

            if line.tax_ids:
                for base_tax in line.tax_ids.flatten_taxes_hierarchy():
                    if tax_ids_filter(line, base_tax):
                        tax_lines_data.append(
                            {
                                'line_key': 'base_line_%s' % line.id,
                                'base_amount': line.amount_currency * balance_multiplier,
                                'tax': base_tax,
                                'tax_affecting_base': line.tax_line_id,
                                'x_balance': line.balance * balance_multiplier,
                                'x_invoice_sign': line.move_id.x_get_invoice_sign(),
                            }
                        )

        return tax_lines_data

    @api.model
    def _get_tax_totals(self, partner, tax_lines_data, amount_total, amount_untaxed, currency):
        result = super()._get_tax_totals(partner, tax_lines_data, amount_total, amount_untaxed, currency)
        if not self.x_get_is_poland():
            return result

        lang_env = self.with_context(lang=partner.lang).env
        account_tax = self.env['account.tax']
        pln = self.env.company.currency_id
        grouped_taxes = defaultdict(
            lambda: defaultdict(
                lambda: {'base_amount': 0.0, 'tax_amount': 0.0, 'x_balance_amount': 0.0, 'base_line_keys': set()}
            )
        )
        tax_amount_in_pln = 0
        subtotal_priorities = {}
        x_invoice_sign = 1

        for line_data in tax_lines_data:
            tax_group = line_data['tax'].tax_group_id
            x_invoice_sign = line_data.get('x_invoice_sign', 1)

            # Update subtotals priorities
            if tax_group.preceding_subtotal:
                subtotal_title = tax_group.preceding_subtotal
                new_priority = tax_group.sequence

            else:
                # When needed, the default subtotal is always the highest priority
                subtotal_title = _("Untaxed Amount")
                new_priority = 0

            if subtotal_title not in subtotal_priorities or new_priority < subtotal_priorities[subtotal_title]:
                subtotal_priorities[subtotal_title] = new_priority

            # Update tax data
            tax_group_vals = grouped_taxes[subtotal_title][tax_group]

            if 'base_amount' in line_data:
                # baseline
                if tax_group == line_data.get('tax_affecting_base', account_tax).tax_group_id:
                    # In case the base has a tax_line_id belonging to the same group as the base tax, the base for
                    # the group will be computed by the base tax's original line (the one with tax_ids and no
                    # tax_line_id)
                    continue

                if line_data['line_key'] not in tax_group_vals['base_line_keys']:
                    # If the baseline hasn't been taken into account yet, at its amount to the base total.
                    tax_group_vals['base_line_keys'].add(line_data['line_key'])
                    tax_group_vals['base_amount'] += line_data['base_amount']

            else:
                # tax line
                balance = line_data.get('x_balance', 0.0)
                tax_group_vals['tax_amount'] += line_data['tax_amount']
                tax_group_vals['x_balance_amount'] += balance
                tax_amount_in_pln += balance

        for groups in grouped_taxes.values():
            for amounts in groups.values():
                for key in ('base_amount', 'tax_amount', 'x_balance_amount'):
                    amounts[key] = x_invoice_sign * abs(amounts.get(key, 0))

        # Compute groups_by_subtotal
        groups_by_subtotal = {}
        for subtotal_title, groups in grouped_taxes.items():
            # noinspection PyTypeChecker
            groups_vals = [
                {
                    'tax_group_name': group.name, # on tax sumary on pdf
                    'tax_group_amount': amounts['tax_amount'],
                    'tax_group_base_amount': amounts['base_amount'],
                    'x_tax_group_total_amount': amounts['tax_amount'] + amounts['base_amount'],
                    'x_tax_group_amount_in_pln': amounts['x_balance_amount'],
                    'formatted_tax_group_amount': formatLang(lang_env, amounts['tax_amount'], currency_obj=currency), # on tax sumary on pdf
                    'formatted_tax_group_base_amount': formatLang(
                        lang_env, amounts['base_amount'], currency_obj=currency
                    ), # on tax sumary on pdf
                    'x_formatted_tax_group_amount_in_pln': formatLang(
                        lang_env, amounts['x_balance_amount'], currency_obj=pln
                    ),
                    'x_formatted_tax_group_total_amount': formatLang(
                        lang_env, amounts['tax_amount'] + amounts['base_amount'], currency_obj=currency
                    ), # on tax sumary on pdf
                    'tax_group_id': group.id,
                    'group_key': '%s-%s' % (subtotal_title, group.id),
                }
                for group, amounts in sorted(groups.items(), key=lambda group: group[0].sequence)
            ]

            groups_by_subtotal[subtotal_title] = groups_vals

        # Compute subtotals
        subtotals_list = []  # List, so that we preserve their order
        previous_subtotals_tax_amount = 0
        for subtotal_title in sorted((sub for sub in subtotal_priorities), key=lambda x: subtotal_priorities[x]):
            subtotal_value = amount_untaxed + previous_subtotals_tax_amount
            subtotals_list.append(
                {
                    'name': subtotal_title, # on tax sumary on view
                    'amount': subtotal_value,
                    'formatted_amount': formatLang(lang_env, subtotal_value, currency_obj=currency), # on tax sumary on view
                }
            )

            subtotal_tax_amount = sum(group_val['tax_group_amount'] for group_val in groups_by_subtotal[subtotal_title])
            previous_subtotals_tax_amount += subtotal_tax_amount

        amount_total = x_invoice_sign * abs(amount_total)
        amount_untaxed = x_invoice_sign * abs(amount_untaxed)
        tax_amount = amount_total - amount_untaxed

        # Assign json-formatted result to the field
        # noinspection PyTypeChecker
        return {
            'amount_total': amount_total, # on tax sumary on pdf
            'amount_untaxed': amount_untaxed, # on tax sumary on pdf
            'formatted_amount_total': formatLang(lang_env, amount_total, currency_obj=currency), # on tax sumary on view
            'formatted_amount_untaxed': formatLang(lang_env, amount_untaxed, currency_obj=currency),
            'groups_by_subtotal': groups_by_subtotal,
            'subtotals': subtotals_list,
            'allow_tax_edition': False,
            'x_tax_amount': tax_amount, # on tax sumary on pdf
            'x_formatted_tax_amount': formatLang(lang_env, tax_amount, currency_obj=currency),
            'x_tax_amount_in_pln': tax_amount_in_pln,
            'x_formatted_tax_amount_in_pln': formatLang(lang_env, tax_amount_in_pln, currency_obj=pln),
        }

    def compute_advance_source_id(self):
        if not self.x_get_is_poland():
            return

        for invoice in self:
            advance_lines = self.env['sale.order.line'].search(
                [
                    ('is_downpayment', '=', True),
                    ('invoice_lines', 'in', invoice.invoice_line_ids.filtered(lambda line: line.credit > 0).ids),
                ]
            )
            invoice.advance_source_id = advance_lines.order_id
            invoice.final_invoice_ids = advance_lines.invoice_lines.filtered(lambda line: line.debit > 0).move_id

    def compute_advance_invoices_ids(self):
        if not self.x_get_is_poland():
            return

        for invoice in self:
            final_lines = self.env['sale.order.line'].search(
                [
                    ('is_downpayment', '=', True),
                    ('invoice_lines', 'in', invoice.invoice_line_ids.filtered(lambda line: line.debit > 0).ids),
                ]
            )
            invoice.advance_invoices_ids = final_lines.invoice_lines.filtered(lambda line: line.credit > 0).move_id
            invoice.final_source_id = False if invoice.refund_invoice_id else final_lines.order_id

    @api.constrains('refund_invoice_id', 'selected_correction_invoice')
    def _x_check_correction_invoice(self):
        if not self.x_get_is_poland():
            return

        for invoice in self:
            if invoice.refund_invoice_id and not invoice.selected_correction_invoice:
                # noinspection PyTypeChecker
                if (
                    self.search(
                        [
                            ('refund_invoice_id', '=', self.refund_invoice_id.id),
                            ('selected_correction_invoice', '=', False),
                        ],
                        count=True,
                    )
                    > 1
                ):
                    raise ValidationError(_('It is not possible to issue two direct corrections for one invoice.'))

            if invoice.refund_invoice_id and invoice.selected_correction_invoice:
                # noinspection PyTypeChecker
                if (
                    self.search(
                        [
                            ('refund_invoice_id', '=', self.refund_invoice_id.id),
                            ('selected_correction_invoice', '=', invoice.selected_correction_invoice.id),
                        ],
                        count=True,
                    )
                    > 1
                ):
                    raise ValidationError(_('It is not possible to issue two direct corrections for one correction.'))

    @api.constrains('state')
    def clock_moving_back(self):
        if not self.x_get_is_poland():
            return

        for invoice in self:
            if invoice.state not in ('draft', 'cancel'):
                continue

            if invoice.correction_invoices_len:
                raise ValidationError(
                    _(
                        'An invoice cannot be modified if it is associated with corrections.\n'
                        'Delete corrections or create a new correction to an existing correction'
                    )
                )

    def get_connected_corrections(self):
        selected_invoice = self
        corrections = self.env['account.move']
        while True:
            correction = self.search([('selected_correction_invoice', '=', selected_invoice.id)])
            if not correction:
                break
            selected_invoice = correction
            corrections += selected_invoice
        return corrections

    @api.depends('refund_invoice_id')
    def _x_compute_original_invoice_line_ids(self):
        for invoice in self:
            if (
                not invoice.x_get_is_poland()
                or invoice.move_type not in ('in_refund', 'out_refund')
                or not invoice.refund_invoice_id
            ):
                invoice.original_invoice_line_ids = False
                continue

            invoice.original_invoice_line_ids = invoice.invoice_line_ids.filtered(
                lambda line: not line.exclude_from_invoice_tab and not line.corrected_line
            ).ids

    @api.depends('invoice_line_ids', 'invoice_line_ids.corrected_line')
    def _x_compute_corrected_invoice_line_ids(self):
        for invoice in self:
            invoice.corrected_invoice_line_ids = invoice.invoice_line_ids.filtered_domain(
                [('exclude_from_invoice_tab', '=', False), ('corrected_line', '=', True)]
            )

    def _x_inverse_corrected_invoice_line_ids(self):
        for invoice in self:
            new_lines = [
                (0, 0, new_line.copy_data()[0])
                for new_line in invoice.corrected_invoice_line_ids.filtered(
                    lambda rec: isinstance(rec.id, models.NewId)
                )
            ]

            if new_lines:
                invoice.invoice_line_ids = new_lines

    @api.depends('correction_invoices_ids', 'move_type')
    def _x_compute_correction_invoices_len(self):
        for invoice in self:
            if invoice.x_get_is_poland():
                if invoice.move_type in ('in_invoice', 'out_invoice'):
                    invoice.correction_invoices_len = len(invoice.correction_invoices_ids)
                else:
                    corrections = invoice.get_connected_corrections()
                    invoice.correction_invoices_len = len(corrections)
            else:
                invoice.correction_invoices_len = 0

    @api.model_create_multi
    def create(self, vals_list):
        if not self.x_get_is_poland():
            return super().create(vals_list)

        if self.env.context.get('x_journal_id', False):
            for vals in vals_list:
                vals['journal_id'] = self.env.context['x_journal_id']

        invoice_ids = super().create(vals_list)
        for invoice, vals in zip(invoice_ids, vals_list):
            refund_invoice_id = vals.get('reversed_entry_id')

            if invoice.move_type in ('in_refund', 'out_refund') and refund_invoice_id:
                invoice.refund_invoice_id = refund_invoice_id

                if invoice.selected_correction_invoice:
                    # correction to the correction
                    invoice.invoice_line_ids.with_context(check_move_validity=False).unlink()
                    for line in invoice.selected_correction_invoice.corrected_invoice_line_ids:
                        copied_vals = line.with_context(
                            include_business_fields=True, check_move_validity=False
                        ).copy_data(
                            default={'move_id': invoice.id, 'price_unit': -line.price_unit, 'corrected_line': False}
                        )[
                            0
                        ]
                        copied = self.env['account.move.line'].create(copied_vals)
                        # copied.price_unit = -line.price_unit
                        copied.quantity = -line.quantity
                        copied.run_onchanges()

                    for line in invoice.selected_correction_invoice.corrected_invoice_line_ids:
                        copied_vals = line.with_context(
                            include_business_fields=True, check_move_validity=False
                        ).copy_data(
                            default={'move_id': invoice.id, 'price_unit': line.price_unit, 'corrected_line': True}
                        )[
                            0
                        ]
                        copied = self.env['account.move.line'].create(copied_vals)
                        copied.quantity = -abs(line.quantity)
                        copied.run_onchanges()

                else:
                    for line in invoice.invoice_line_ids:
                        copied_vals = line.with_context(
                            include_business_fields=True, check_move_validity=False
                        ).copy_data(default={'move_id': invoice.id, 'corrected_line': True})[0]
                        copied = self.env['account.move.line'].create(copied_vals)
                        copied.quantity = -line.quantity
                        copied.run_onchanges()

                invoice.with_context(check_move_validity=False)._onchange_invoice_line_ids()
                invoice._compute_tax_totals_json()

        return invoice_ids

    @api.constrains('corrected_invoice_line_ids', 'move_type')
    def constrains_correction_data(self):
        if not self.x_get_is_poland():
            return

        for invoice in self:
            if invoice.move_type in ('in_refund', 'out_refund') and invoice.corrected_invoice_line_ids:

                for line in invoice.invoice_line_ids:
                    line.run_onchanges()

                invoice._onchange_invoice_line_ids()
                invoice._recompute_dynamic_lines(True)
                invoice._compute_tax_totals_json()

    def correction_invoices_view(self):
        view_data = {
            'name': _('Correction Invoices'),
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
        }

        if self.move_type in ('in_invoice', 'out_invoice'):
            view_data['domain'] = [('id', 'in', self.correction_invoices_ids.ids)]

        else:
            view_data['domain'] = [('id', 'in', self.get_connected_corrections().ids)]

        return view_data

    def action_reverse(self):
        if not self.x_get_is_poland():
            return super().action_reverse()

        ctx = dict(self.env.context)
        rec = self

        if self.refund_invoice_id:
            ctx['active_id'] = self.refund_invoice_id.id
            ctx['active_ids'] = [self.refund_invoice_id.id]
            rec = self.refund_invoice_id
        rec = rec.with_context(ctx)
        action = rec.env.ref('account.action_view_account_move_reversal').read()[0]
        if rec.is_invoice():
            action['name'] = _('Credit Note')

        return action

    # changes in existing methods

    def action_post(self):
        if not self.x_get_is_poland():
            return super().action_post()

        for invoice in self:
            if invoice.move_type in ('in_invoice', 'in_receipt', 'in_refund') and not invoice.ref:
                raise ValidationError(_('Vendor invoice number is required'))

        return super(AccountMove, self.with_context(x_block_changing_price=True)).action_post()

    def _post(self, soft=True):
        if not self.x_get_is_poland():
            return super()._post()

        invoice_ids = self.browse()
        correction_ids = self.browse()

        for move_id in self:
            # update x_invoice_sale_date if not set
            if move_id.move_type != 'entry' and not move_id.x_invoice_sale_date:
                if not move_id.invoice_date:
                    if move_id.is_sale_document(include_receipts=True):
                        move_id.x_invoice_sale_date = fields.Date.context_today(move_id)

                    elif move_id.is_purchase_document(include_receipts=True):
                        raise UserError(_('The Bill/Refund date is required to validate this document.'))

                else:
                    move_id.x_invoice_sale_date = move_id.invoice_date

                # move_id.x_onchange_set_currency_rate()
                move_id = move_id._x_update_context_with_currency_rate()

            if (
                move_id.move_type in ('out_refund', 'in_refund')
                and float_compare(move_id.amount_total, 0.0, precision_rounding=move_id.currency_id.rounding) < 0
            ):
                correction_ids |= move_id

            else:
                invoice_ids |= move_id

        return super(AccountMove, invoice_ids)._post(soft) | correction_ids._x_post_wo_validation(soft)

    # noinspection PyPep8,PyPep8Naming,PyShadowingNames
    def _x_post_wo_validation(self, soft=True):
        """This is a copy of the original _post method with one section commented out:
        raising exception on negative amount
        """
        if soft:
            future_moves = self.filtered(lambda move: move.date > fields.Date.context_today(self))
            future_moves.auto_post = True
            for move in future_moves:
                msg = _(
                    'This move will be posted at the accounting date: %(date)s', date=format_date(self.env, move.date)
                )
                move.message_post(body=msg)
            to_post = self - future_moves
        else:
            to_post = self

        # `user_has_group` won't be bypassed by `sudo()` since it doesn't change the user anymore.
        if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_("You don't have the access rights to post an invoice."))
        for move in to_post:
            if move.partner_bank_id and not move.partner_bank_id.active:
                raise UserError(
                    _(
                        "The recipient bank account link to this invoice is archived.\n"
                        "So you cannot confirm the invoice."
                    )
                )
            if move.state == 'posted':
                raise UserError(_('The entry %s (id %s) is already posted.') % (move.name, move.id))
            if not move.line_ids.filtered(lambda line: not line.display_type):
                raise UserError(_('You need to add a line before posting.'))
            if move.auto_post and move.date > fields.Date.context_today(self):
                date_msg = move.date.strftime(get_lang(self.env).date_format)
                raise UserError(_("This move is configured to be auto-posted on %s", date_msg))
            if not move.journal_id.active:
                raise UserError(
                    _("You cannot post an entry in an archived journal (%(journal)s)", journal=move.journal_id.name)
                )

            if not move.partner_id:
                if move.is_sale_document():
                    raise UserError(
                        _("The field 'Customer' is required, please complete it to validate the Customer Invoice.")
                    )
                elif move.is_purchase_document():
                    raise UserError(
                        _("The field 'Vendor' is required, please complete it to validate the Vendor Bill.")
                    )

            # CHANGE TO DEFAULT METHOD
            # if (
            #     move.is_invoice(include_receipts=True)
            #     and float_compare(move.amount_total, 0.0, precision_rounding=move.currency_id.rounding) < 0
            # ):
            #     raise UserError(
            #         _(
            #             "You cannot validate an invoice with a negative total amount. "
            #             "You should create a credit note instead. "
            #             "Use the action menu to transform it into a credit note or refund."
            #         )
            #     )

            if move.display_inactive_currency_warning:
                raise UserError(
                    _("You cannot validate an invoice with an inactive currency: %s", move.currency_id.name)
                )

            # Handle case when the invoice_date is not set. In that case, the invoice_date is set at today and then,
            # lines are recomputed accordingly.
            # /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
            # environment.
            if not move.invoice_date:
                if move.is_sale_document(include_receipts=True):
                    move.invoice_date = fields.Date.context_today(self)
                    move.with_context(check_move_validity=False)._onchange_invoice_date()
                elif move.is_purchase_document(include_receipts=True):
                    raise UserError(_("The Bill/Refund date is required to validate this document."))

            # When the accounting date is prior to a lock date, change it automatically upon posting.
            # /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
            # environment.
            affects_tax_report = move._affect_tax_report()
            lock_dates = move._get_violated_lock_dates(move.date, affects_tax_report)
            if lock_dates:
                move.date = move._get_accounting_date(move.invoice_date or move.date, affects_tax_report)
                if move.move_type and move.move_type != 'entry':
                    move.with_context(check_move_validity=False)._onchange_currency()

        # Create the analytic lines in batch is faster as it leads to less cache invalidation.
        to_post.mapped('line_ids').create_analytic_lines()

        for move in to_post:
            # Fix inconsistencies that may occur if the OCR has been editing the invoice at the same time of a user.
            # We force the partner on the lines to be the same as the one on the move, because that's the only one the
            # user can see/edit.
            wrong_lines = move.is_invoice() and move.line_ids.filtered(
                lambda aml: aml.partner_id != move.commercial_partner_id and not aml.display_type
            )
            if wrong_lines:
                wrong_lines.write({'partner_id': move.commercial_partner_id.id})

        to_post.write({'state': 'posted', 'posted_before': True})

        for move in to_post:
            move.message_subscribe([p.id for p in [move.partner_id] if p not in move.sudo().message_partner_ids])

            # Compute 'ref' for 'out_invoice'.
            if move._auto_compute_invoice_reference():
                to_write = {'payment_reference': move._get_invoice_computed_reference(), 'line_ids': []}
                for line in move.line_ids.filtered(
                    lambda line: line.account_id.user_type_id.type in ('receivable', 'payable')
                ):
                    to_write['line_ids'].append((1, line.id, {'name': to_write['payment_reference']}))
                move.write(to_write)

        for move in to_post:
            if (
                move.is_sale_document()
                and move.journal_id.sale_activity_type_id
                and (move.journal_id.sale_activity_user_id or move.invoice_user_id).id
                not in (self.env.ref('base.user_root').id, False)
            ):
                move.activity_schedule(
                    date_deadline=min(
                        (date for date in move.line_ids.mapped('date_maturity') if date), default=move.date
                    ),
                    activity_type_id=move.journal_id.sale_activity_type_id.id,
                    summary=move.journal_id.sale_activity_note,
                    user_id=move.journal_id.sale_activity_user_id.id or move.invoice_user_id.id,
                )

        customer_count, supplier_count = defaultdict(int), defaultdict(int)
        for move in to_post:
            if move.is_sale_document():
                customer_count[move.partner_id] += 1
            elif move.is_purchase_document():
                supplier_count[move.partner_id] += 1
        for partner, count in customer_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('customer_rank', count)
        for partner, count in supplier_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('supplier_rank', count)

        # Trigger action for paid invoices in amount is zero
        to_post.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.currency_id.is_zero(m.amount_total)
        ).action_invoice_paid()

        # Force balance check since nothing prevents another module to create an incorrect entry.
        # This is performed at the very end to avoid flushing fields before the whole processing.
        to_post._check_balanced()
        return to_post

    def _compute_payments_widget_to_reconcile_info(self):
        if not self.x_get_is_poland():
            return super()._compute_payments_widget_to_reconcile_info()

        for move in self:
            move.invoice_outstanding_credits_debits_widget = json.dumps(False)
            move.invoice_has_outstanding = False

            if (
                move.state != 'posted'
                or move.payment_state not in ('not_paid', 'partial')
                or not move.is_invoice(include_receipts=True)
            ):
                continue

            pay_term_line_ids = move.line_ids.filtered(
                lambda _line: _line.account_id.user_type_id.type in ('receivable', 'payable')
            )

            domain = [
                ('account_id', 'in', pay_term_line_ids.mapped('account_id').ids),
                '|',
                ('move_id.state', '=', 'posted'),
                ('move_id.state', '=', 'draft'),
                ('partner_id', '=', move.commercial_partner_id.id),
                ('reconciled', '=', False),
                '|',
                ('amount_residual', '!=', 0.0),
                ('amount_residual_currency', '!=', 0.0),
            ]

            if move.is_inbound():
                if move.amount_total < 0:
                    domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                    type_payment = _('Outstanding debits')

                else:
                    domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                    type_payment = _('Outstanding credits')

            else:
                if move.amount_total < 0:
                    domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                    type_payment = _('Outstanding credits')

                else:
                    domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                    type_payment = _('Outstanding debits')

            info = {'title': '', 'outstanding': True, 'content': [], 'move_id': move.id}
            lines = self.env['account.move.line'].search(domain)
            currency_id = move.currency_id

            if len(lines) != 0:
                for line in lines:
                    # get the outstanding residual value in invoice currency
                    if line.currency_id and line.currency_id == move.currency_id:
                        amount_to_show = abs(line.amount_residual_currency)

                    else:
                        currency = line.company_id.currency_id
                        amount_to_show = currency._convert(
                            abs(line.amount_residual),
                            move.currency_id,
                            move.company_id,
                            line.date or fields.Date.today(),
                        )

                    if move.currency_id.is_zero(amount_to_show):
                        continue

                    info['content'].append(
                        {
                            'journal_name': line.ref or line.move_id.name,
                            'amount': amount_to_show,
                            'currency': currency_id.symbol,
                            'id': line.id,
                            'move_id': line.move_id.id,  # ?
                            'position': currency_id.position,
                            'digits': [69, move.currency_id.decimal_places],
                            'payment_date': fields.Date.to_string(line.date),
                        }
                    )

                info['title'] = type_payment
                move.invoice_outstanding_credits_debits_widget = json.dumps(info)
                move.invoice_has_outstanding = True

    # noinspection PyMethodMayBeStatic
    def _format_float(self, number, currency, env):
        return formatLang(env, 0.0 if currency.is_zero(number) else number, currency_obj=currency)

    # noinspection PyUnresolvedReferences,PyTypeChecker
    @api.depends(
        'line_ids.price_subtotal',
        'line_ids.tax_base_amount',
        'line_ids.tax_line_id',
        'partner_id',
        'currency_id',
        'refund_invoice_id',
    )
    def _x_compute_invoice_taxes_by_group(self):
        pln = self.env.ref('base.PLN')

        for move in self:
            move.x_corrected_amount_by_group = []
            move.x_corrected_amount_summary = []

            if not move.is_invoice(include_receipts=True) or not move.refund_invoice_id:
                continue

            lang_env = move.with_context(lang=move.partner_id.lang).env
            balance_multiplicator = -1 if move.move_type.endswith('_refund') else 1

            for corr in move.amount_by_group:
                move.x_corrected_amount_by_group.append(
                    (
                        corr[0],
                        -corr[1],
                        -corr[2],
                        self._format_float(-corr[1], move.currency_id, lang_env),
                        self._format_float(-corr[2], move.currency_id, lang_env),
                        corr[5],
                        corr[6],
                        self._format_float(-corr[8], pln, lang_env),
                        -corr[8],
                    )
                )

            amount_summary = move.refund_invoice_id.x_invoice_amount_summary.copy()

            for key in ('base', 'amount', 'in_pln', 'total'):
                f_key = f'{key}_float'
                amount_summary[f_key] += balance_multiplicator * move.x_invoice_amount_summary[f_key]
                amount_summary[key] = formatLang(lang_env, amount_summary[f_key], currency_obj=move.currency_id)

            amount_summary['in_pln'] = formatLang(lang_env, amount_summary['in_pln_float'], currency_obj=pln)

            move.x_corrected_amount_summary = amount_summary

    @api.depends(
        'line_ids.price_subtotal', 'line_ids.tax_base_amount', 'line_ids.tax_line_id', 'partner_id', 'currency_id'
    )
    def x_get_invoice_amount_summary(self):
        self.ensure_one()
        pln = self.env.ref('base.PLN')

        # Not working on something else than invoices.
        if not self.is_invoice(include_receipts=True):
            return {}

        lang_env = self.with_context(lang=self.partner_id.lang).env
        balance_multiplicator = -1 if self.is_inbound() else 1

        tax_lines = self.line_ids.filtered('tax_line_id')
        base_lines = self.line_ids.filtered('tax_ids') | self.invoice_line_ids

        tax_group_mapping = defaultdict(
            lambda: {'base_lines': set(), 'base_amount': 0.0, 'tax_amount': 0.0, 'in_pln': 0.0}
        )
        # noinspection PyPep8Naming
        EmptyTaxGroup = self.env['account.tax.group']

        # Compute base amounts.
        for base_line in base_lines:
            base_amount = balance_multiplicator * (
                base_line.amount_currency if base_line.currency_id else base_line.balance
            )

            for tax in base_line.tax_ids.flatten_taxes_hierarchy():

                if base_line.tax_line_id.tax_group_id == tax.tax_group_id:
                    continue

                tax_group_vals = tax_group_mapping[tax.tax_group_id]
                if base_line not in tax_group_vals['base_lines']:
                    tax_group_vals['base_amount'] += base_amount
                    tax_group_vals['base_lines'].add(base_line)

            if not base_line.tax_ids and base_line not in tax_group_mapping[EmptyTaxGroup]['base_lines']:
                tax_group_vals = tax_group_mapping[EmptyTaxGroup]
                tax_group_vals['base_amount'] += base_amount
                tax_group_vals['base_lines'].add(base_line)

        # Compute tax amounts.
        for tax_line in tax_lines:
            tax_amount = balance_multiplicator * (
                tax_line.amount_currency if tax_line.currency_id else tax_line.balance
            )
            tax_group_vals = tax_group_mapping[tax_line.tax_line_id.tax_group_id]
            tax_group_vals['tax_amount'] += tax_amount
            tax_group_vals['in_pln'] += balance_multiplicator * tax_line.balance

        tax_groups = sorted(tax_group_mapping.keys(), key=lambda x: x.sequence)
        amount_by_group = []
        for tax_group in tax_groups:
            tax_group_vals = tax_group_mapping[tax_group]
            # noinspection PyTypeChecker
            amount_by_group.append(
                (
                    tax_group.name,
                    tax_group_vals['tax_amount'],
                    tax_group_vals['base_amount'],
                    formatLang(lang_env, tax_group_vals['tax_amount'], currency_obj=self.currency_id),
                    formatLang(lang_env, tax_group_vals['base_amount'], currency_obj=self.currency_id),
                    len(tax_group_mapping),
                    tax_group.id,
                    formatLang(lang_env, tax_group_vals['in_pln'], currency_obj=pln),
                    tax_group_vals['in_pln'],
                )
            )

        summary = {'base_amount': 0.0, 'tax_amount': 0.0, 'in_pln': 0.0}

        for tax_group_vals in tax_group_mapping.values():
            summary['base_amount'] += tax_group_vals['base_amount']
            summary['tax_amount'] += tax_group_vals['tax_amount']
            summary['in_pln'] += tax_group_vals['in_pln']

        summary.update(
            {
                'base_amount': abs(summary['base_amount']) * self.x_invoice_sign,
                'tax_amount': abs(summary['tax_amount']) * self.x_invoice_sign,
                'in_pln': abs(summary['in_pln']) * self.x_invoice_sign,
            }
        )

        return {
            'base': self._format_float(summary['base_amount'], self.currency_id, lang_env),
            'base_float': summary['base_amount'],
            'amount': self._format_float(summary['tax_amount'], self.currency_id, lang_env),
            'amount_float': summary['tax_amount'],
            'in_pln': self._format_float(summary['in_pln'], pln, lang_env),
            'in_pln_float': summary['in_pln'],
            'total': self._format_float((summary['base_amount'] + summary['tax_amount']), self.currency_id, lang_env),
            'total_float': summary['base_amount'] + summary['tax_amount'],
        }

    def _reverse_move_vals(self, default_values, cancel=True):
        if not self.x_get_is_poland():
            return super()._reverse_move_vals(default_values, cancel)

        force_type = None
        if 'selected_correction_invoice' in default_values and default_values['selected_correction_invoice']:
            selected_correction_invoice_id = self.browse([default_values['selected_correction_invoice']])
            force_type = selected_correction_invoice_id.move_type

        result = super()._reverse_move_vals(default_values, cancel)

        # _reverse_move_vals is removing partner_bank_id from default values, bringing it back
        if 'partner_bank_id' not in result and 'partner_bank_id' in default_values:
            result['partner_bank_id'] = default_values['partner_bank_id']

        if force_type:
            result['move_type'] = force_type

        return result

    def action_reverse_pl(self):
        action = self.env.ref('trilab_invoice.action_view_account_move_reversal_pl').sudo().read()[0]

        if self.is_invoice():
            action['name'] = _('Credit Note PL')

        return action

    def x_num2words(self, amount: float, currency):
        amount = '{:.2f}'.format(amount)
        lang = self.env.context.get('lang', 'en')
        # If template preview
        tmpl_id = self._context.get('default_mail_template_id')
        if tmpl_id:
            template = self.env['mail.template'].browse([tmpl_id])
            if template.lang:
                lang = template._render_lang(self.ids)[self.id]

        try:
            # noinspection PyPackageRequirements
            from num2words import num2words

            # noinspection PyBroadException
            try:
                return num2words(amount, lang=lang, to='currency', currency=currency)

            except NotImplementedError:
                _logger.warning('num2words - unsupported language')
                return ''

            except Exception:
                # currency convert unsupported for this language (no proper exception returned)
                return num2words(amount, lang=lang)

        except ImportError:
            _logger.warning('num2words not installed, no text2word for invoice')
            return ''

        except Exception as e:
            _logger.error('num2words - %s', e)
            return ''

    @api.depends(
        'corrected_invoice_line_ids.quantity',
        'corrected_invoice_line_ids.price_unit',
        'corrected_invoice_line_ids.discount',
        'refund_invoice_id',
    )
    def _x_compute_corrected_amount_total(self):
        if not self.x_get_is_poland():
            return

        for move in self:
            move.x_corrected_amount_total = move.amount_total
            if move.refund_invoice_id:
                x_corrected_amount_total = 0

                for line in move.corrected_invoice_line_ids:
                    x_corrected_amount_total += line._get_price_total_and_subtotal(quantity=line.x_quantity_reverse)[
                        'price_total'
                    ]
                move.x_corrected_amount_total = x_corrected_amount_total

    def x_get_invoice_sign(self):
        self.ensure_one()
        if (
            self.move_type in ('out_refund', 'in_refund')
            and not float_compare(self.x_corrected_amount_total, self.refund_invoice_id.x_corrected_amount_total, 2)
            >= 0
        ):
            return -1

        return 1

    @api.depends('move_type', 'refund_invoice_id.amount_total', 'amount_total', 'x_corrected_amount_total')
    def x_compute_invoice_sign(self):
        for move in self:
            move.x_invoice_sign = move.x_get_invoice_sign()

    @api.depends('amount_total', 'amount_residual')
    def _x_compute_amount(self):
        for move in self:
            total_residual = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            # noinspection PyProtectedMember
            currencies = move._get_lines_onchange_currency().currency_id

            for line in move.line_ids:
                if move.is_invoice(include_receipts=True):
                    if not line.exclude_from_invoice_tab:
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.tax_line_id:
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.account_id.user_type_id.type in ('receivable', 'payable'):

                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            if move.is_purchase_document():
                sign = -1
            else:
                sign = 1

            move.x_amount_total = sign * abs(total_currency if len(currencies) == 1 else total)
            move.x_amount_residual = total_residual_currency if len(currencies) == 1 else total_residual

            
    # [UPGRADE] START
    @api.depends(
        'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state',
        'line_ids.full_reconcile_id')
    def _compute_amount(self):   
        super()._compute_amount()
        for move in self:
            # _logger.info("========================\n" + str(move.name) + "\n" + str(move.x_amount_total) + "\n" + str(move.x_amount_residual) + "\n" + str(move.amount_residual))
            move.amount_residual = move.x_amount_residual
    # [UPGRADE] END


    def _move_autocomplete_invoice_lines_write(self, vals):
        res = super()._move_autocomplete_invoice_lines_write(vals)

        enable_autocomplete = (
            self.x_get_is_poland() and 'corrected_invoice_line_ids' in vals and 'line_ids' not in vals and True or False
        )

        if not enable_autocomplete:
            return res

        vals['line_ids'] = vals.pop('corrected_invoice_line_ids')
        for invoice in self:
            invoice_new = invoice.with_context(
                default_move_type=invoice.move_type,
                default_journal_id=invoice.journal_id.id,
                default_partner_id=invoice.partner_id.id,
                default_currency_id=invoice.currency_id.id,
            ).new(origin=invoice)
            invoice_new.update(vals)
            values = invoice_new._move_autocomplete_invoice_lines_values()
            values.pop('invoice_line_ids', None)
            invoice.write(values)

        return True

    def _x_update_context_with_currency_rate(self, obj=None, currency_rate=None, force=False):

        if obj is None:
            obj = self

        if (
            self.x_show_currency_rate
            and ('x_trilab_force_currency_rate' not in self._context or force)
            and (not self.company_currency_id.is_zero(self.x_currency_rate) or currency_rate)
        ):
            return obj.with_context(x_trilab_force_currency_rate=currency_rate or self.x_currency_rate)
        return obj

    def x_update_currency_rate(self):
        if self.x_show_currency_rate:
            _x_rate = self.x_currency_rate

            self.x_currency_rate = self.env['res.currency']._get_conversion_rate(
                self.currency_id,
                self.company_currency_id,
                self.company_id or self.env.company,
                self.x_invoice_sale_date or self.invoice_date or self.date or fields.Date.context_today(self),
            )

            if float_compare(_x_rate, self.x_currency_rate, precision_digits=4) != 0:
                return self.with_context(x_currency_rate_changed=True)

        return self

    @api.onchange('x_invoice_sale_date', 'invoice_date', 'currency_id', 'company_id', 'date')
    def _x_onchange_set_currency_rate(self):
        if self.x_show_currency_rate:
            recs = self.x_update_currency_rate()
            recs = recs._x_update_context_with_currency_rate()

            if recs._context.get('x_currency_rate_changed', False):
                recs._onchange_recompute_dynamic_lines()
                # recs._onchange_currency()
                recs.line_ids._onchange_amount_currency()

    @api.onchange('x_currency_rate')
    def _x_onchange_currency_rate(self):
        if self.x_show_currency_rate:
            recs = self.with_context(x_currency_rate_changed=True)._x_update_context_with_currency_rate()

            if recs._context.get('x_currency_rate_changed', False):
                recs._onchange_recompute_dynamic_lines()
                # recs._onchange_currency()
                recs.line_ids._onchange_amount_currency()

    def _recompute_dynamic_lines(self, recompute_all_taxes=False, recompute_tax_base_amount=False):
        if self.x_show_currency_rate:
            # if not self._context.get('x_currency_rate_changed'):
            #     self = self.x_update_currency_rate()

            self = self._x_update_context_with_currency_rate()

            if 'x_currency_rate_changed' in self._context:
                self.line_ids._onchange_currency()

        return super()._recompute_dynamic_lines(recompute_all_taxes, recompute_tax_base_amount)

    @api.onchange('date', 'currency_id', 'x_invoice_sale_date')
    def _onchange_currency(self):
        # self.x_onchange_set_currency_rate()
        self = self.x_update_currency_rate()
        self = self._x_update_context_with_currency_rate()
        super(AccountMove, self)._onchange_currency()

    @api.depends('company_id.x_enable_invoice_rate_change', 'currency_id', 'company_currency_id')
    def _x_compute_show_currency_rate(self):
        for move in self:
            move.x_show_currency_rate = (
                self.x_get_is_poland()
                and move.company_id.x_enable_invoice_rate_change
                and move.currency_id != move.company_currency_id
            )

    def x_is_jpk_mpp(self):
        """Checking whether account_move has field 'x_pl_vat_mpp (extension from 'trilab_jpk_base' module"""
        self.ensure_one()
        return bool(getattr(self, 'x_pl_vat_mpp', False))

    @api.onchange('invoice_date')
    def _x_onchange_invoice_date(self):
        for invoice in self:
            if invoice.move_type != 'entry' and not invoice.x_invoice_sale_date:
                invoice.x_invoice_sale_date = invoice.invoice_date

    @api.depends('commercial_partner_id', 'move_type')
    def _compute_bank_partner_id(self):
        if not self.x_get_is_poland():
            return super()._compute_bank_partner_id()

        for move in self:
            if move.is_inbound() or move.move_type == 'out_refund':
                move.bank_partner_id = move.company_id.partner_id
            else:
                move.bank_partner_id = move.commercial_partner_id
