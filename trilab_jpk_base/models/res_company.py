from odoo import api, fields, models
import re


class Company(models.Model):
    _inherit = 'res.company'

    pl_tax_office_id = fields.Many2one('jpk.taxoffice', string='PL Tax Office')
    pl_county = fields.Char('County')
    pl_community = fields.Char('Community')
    pl_post = fields.Char('Post')

    x_street_short = fields.Char(string='Street (without house number)', compute='_x_split_street_no', store=False)
    x_street_short_number = fields.Char(string='House Number', store=False)

    @api.depends('street', 'street2')
    def _x_split_street_no(self):
        for company in self.sudo():
            street = ' '.join((company.street or '', company.street2 or '')).strip()
            parts = re.split(r'\s(?=\d)', street)
            company.x_street_short = parts[0]
            company.x_street_short_number = parts[1] if len(parts) > 1 else None
