from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError
 
 
@tagged('myodoo')
class TestSaleOrder(TransactionCase):
 
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env['res.company'].create({
            'name': 'test_company'
        })
        
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
       })

        cls.currency = cls.env['res.currency'].create({
            'name': 'American Dollar',
            'symbol': 'USD'
        })

        cls.sale_order = cls.env['sale.order'].create({
            'name': 'SO123',
            'partner_id': cls.partner.id,
            'currency_id': cls.currency.id
        })

        cls.product_1 = cls.env['product.product'].create({
            'name': 'test_product'
        })

        cls.product_2 = cls.env['product.product'].create({
            'name': 'prod_test'
        })

        cls.tax_group = cls.env['account.tax.group'].create ({
            'name': 'group_name',
        })

        cls.country = cls.env['res.country'].search([('name', '=', 'Poland')])


        cls.tax = cls.env['account.tax'].create({
            'amount': 23,
            'amount_type': 'percent',
            'company_id': cls.company.id,
            'country_id': cls.country.id,
            'name': '23%',
            'tax_group_id': cls.tax_group.id,
            'type_tax_use': 'sale'
        })

        cls.so_line_1 = cls.env['sale.order.line'].create({
            'product_id': cls.product_1.id,
            'price_unit': 15.05,
            'product_uom_qty': 1.0,
            'order_id': cls.sale_order.id
        })

        cls.so_line_2 = cls.env['sale.order.line'].create({
            'product_id': cls.product_2.id,
            'price_unit': 21.22,
            'product_uom_qty': 3.0,
            'order_id': cls.sale_order.id
        })

    
    def test_x_get_taxes_summary(self):
        """
        This method also uses method get_taxes_group(), so two methods will be tested by one test method.
        """
        summary = {
            'base': sum(self.currency.round(line.price_subtotal) for line in self.sale_order.order_line)
        }
        summary['tax'] = self.currency.round(summary['base'] * (self.tax.amount / 100))
        summary['total'] = self.currency.round(summary['base'] + summary['tax'])
        
        self.assertEqual(self.sale_order.x_get_taxes_summary(),
                        summary,
                        'Taxes of SO computed incorrectly.')

    def test_check_advance_invoice_values(self):
        self.assertRaises(UserError,
                          self.sale_order.check_advance_invoice_values())

    def test__x_prepare_invoice_line(self):
        quantity = sum(line.qty_to_invoice for line in self.sale_order.order_line)
        method_res = self.so_line_1._x_prepare_invoice_line(sequence=1)['quantity'] + self.so_line_2._x_prepare_invoice_line(sequence=1)['quantity']
        self.assertEqual(quantity,
                        method_res,
                        'quantity of sale order computed incorrectly.')
