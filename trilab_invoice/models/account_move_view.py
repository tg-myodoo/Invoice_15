from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # [UPGRADE] START
        # variable added to fix outputs used by odoo's widgets:
        # invoice preview and invoice mail templates
        # by creating new fields:  
    amount_total_for_view = fields.Monetary(string='fixed amount total in Currency for view purposes', compute='_compute_amount_for_view')
    amount_residual_for_view = fields.Monetary(string='fixed amount residual in Currency for view purposes', compute='_compute_amount_for_view')
    
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
    def _compute_amount_for_view(self):   
    # method added to fix outputs used by odoo's widgets:
    # invoice preview and invoice mail templates  
    # by creating new (computed below) fields:  
        for move in self:
            move.amount_residual_for_view = move.x_amount_residual
            if move.move_type in ('in_invoice', 'in_refund'):
                move.amount_residual_for_view = abs(move.x_amount_residual) if move.move_type in ('in_invoice') else -move.x_amount_residual
            move.amount_total_for_view = abs(move.amount_total) if move.move_type  in ('in_invoice', 'out_invoice', 'entry') else -move.amount_total
    # [UPGRADE] END