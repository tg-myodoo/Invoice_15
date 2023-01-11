from odoo.tests import TransactionCase, tagged

from datetime import datetime
import logging
_logger = logging.getLogger(__name__)


@tagged('myodoo')
class TestAccountMove(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up data for all tests in this test class."""
        super(TestAccountMove, cls).setUpClass()
        _logger.info(f'BEGINNING OF "account_move" MODULE UNIT TESTS!')

        # Sale journal creation with setting currency.
        cls.currency_pln_id = cls.env.ref("base.PLN")
        cls.currency_pln_id.active = True

        cls.journal_sale = cls.env['account.journal'].create({
            'name': 'Sale Journal - Test',
            'code': 'AJ-SALE',
            'type': 'sale',
            'currency_id': cls.currency_pln_id.id,
            'company_id': cls.env.user.company_id.id
        })

        # Test user
        cls.test_user = cls.env['res.users'].create({
            'name': 'Test_User',
            'login': 'test@test.pl'
        })

        # Test country and company.
        cls.country = cls.env['res.country'].search([('name', '=', 'Poland')])
        
        cls.company = cls.env['res.company'].create({
            'name': 'Company Name',
            'country_id': cls.country.id
        })

        # Account.
        user_type_payable = cls.env.ref('account.data_account_type_payable')
        cls.account_payable = cls.env['account.account'].create({
            'code': 'NC1110',
            'name': 'Test Payable Account',
            'user_type_id': user_type_payable.id,
            'reconcile': True
        })
        user_type_receivable = cls.env.ref('account.data_account_type_receivable')
        cls.account_receivable = cls.env['account.account'].create({
            'code': 'NC1111',
            'name': 'Test Receivable Account',
            'user_type_id': user_type_receivable.id,
            'reconcile': True
        })

        # Create test partners.
        cls.company_partner_1 = cls.env['res.partner'].create({
            'name': 'Partner Company 1',
            'type': 'contact',
            'vat': 'PL9222367183',
            'company_type': 'company',
            'property_account_payable_id': cls.account_payable.id,
            'property_account_receivable_id': cls.account_receivable.id
        })
        cls.person_partner_1 = cls.env['res.partner'].create({
            'name': 'Partner Person 1',
            'type': 'contact',
            'company_type': 'person',
            'parent_id': cls.company_partner_1.id,
            'property_account_payable_id': cls.account_payable.id,
            'property_account_receivable_id': cls.account_receivable.id
        })

        # Create test products.
        cls.test_product_1 = cls.env['product.product'].create({
            'name': 'Test Product 1',
            'sale_ok': True
        })
        cls.test_product_2 = cls.env['product.product'].create({
            'name': 'Test Product 2',
            'sale_ok': True
        })

        # # Create sale orders
        # cls.test_sale_order = cls.env['sale_order'].create({
        #     'partner_id': cls.company_partner_1.id
        #     # 'x_is_poland': False
        # })

        # cls.test_sale_order_line = cls.env['sale_order_line'].create({
        #     'order_id': cls.test_sale_order.id,
        #     'product_id': cls.test_product_1.id
        # })

        # Create test invoices
        cls.test_invoice_1 = cls.env['account.move'].create({
            'name': 'INV/001',
            'partner_id': cls.company_partner_1.id,
            'move_type': 'out_invoice',
            'journal_id': cls.journal_sale.id,
            'currency_id': cls.currency_pln_id.id,
            'invoice_date': datetime.strptime('20-12-2022', '%d-%m-%Y'),
            'invoice_line_ids': [(0, 0, {
                'product_id': cls.test_product_1.id,
                'quantity': 1,
                'price_unit': 100.0,
                'account_id': cls.account_receivable.id
            })],
            'line_ids': [(0, 0, {
                'name': 'debit',
                'account_id': cls.account_payable.id,
                'debit': 100.0,
                'credit': 0.0
            }), (0, 0, {
                'name': 'credit',
                'account_id': cls.account_receivable.id,
                'debit': 0.0,
                'credit': 100.0
            })]
        })

        # cls.test_invoice_2 = cls.env['account.move'].create({
        #     'name': 'INV/002',
        #     'partner_id': cls.company_partner_1.id,
        #     'move_type': 'out_invoice',
        #     'date': datetime.strptime('20-12-2022', '%d-%m-%Y'),
        #     'line_ids': [
        #         (0, None, {
        #             'name': 'revenue line 1',
        #             'account_id': cls.company_data['default_account_revenue'].id,
        #             'debit': 500.0,
        #             'credit': 0.0,
        #         }),
        #         (0, None, {
        #             'name': 'revenue line 2',
        #             'account_id': cls.company_data['default_account_revenue'].id,
        #             'debit': 1000.0,
        #             'credit': 0.0,
        #             'tax_ids': [(6, 0, cls.company_data['default_tax_sale'].ids)],
        #         }),
        #         (0, None, {
        #             'name': 'tax line',
        #             'account_id': cls.company_data['default_account_tax_sale'].id,
        #             'debit': 150.0,
        #             'credit': 0.0,
        #             # 'tax_repartition_line_id': tax_repartition_line.id,
        #         }),
        #         (0, None, {
        #             'name': 'counterpart line',
        #             'account_id': cls.company_data['default_account_expense'].id,
        #             'debit': 0.0,
        #             'credit': 1650.0,
        #         }),
        #     ]
        # })

        cls.test_refund_3 = cls.env['account.move'].create({
            'name': 'RINV/003',
            'partner_id': cls.company_partner_1.id,
            'move_type': 'out_refund',
            'journal_id': cls.journal_sale.id,
            'currency_id': cls.currency_pln_id.id,
            'invoice_date': datetime.strptime('20-12-2022', '%d-%m-%Y'),
            'invoice_line_ids': [(0, 0, {
                'product_id': cls.test_product_1.id,
                'quantity': 1,
                'price_unit': 100.0,
                'account_id': cls.account_receivable.id
            })],
            'line_ids': [(0, 0, {
                'name': 'debit',
                'account_id': cls.account_payable.id,
                'debit': 100.0,
                'credit': 0.0
            }), (0, 0, {
                'name': 'credit',
                'account_id': cls.account_receivable.id,
                'debit': 0.0,
                'credit': 100.0
            })],
        })

        cls.test_invoice_3 = cls.env['account.move'].create({
            'name': 'INV/003',
            'partner_id': cls.company_partner_1.id,
            'move_type': 'out_refund',
            'journal_id': cls.journal_sale.id,
            'currency_id': cls.currency_pln_id.id,
            'invoice_date': datetime.strptime('20-12-2022', '%d-%m-%Y'),
            'invoice_line_ids': [(0, 0, {
                'product_id': cls.test_product_1.id,
                'quantity': 1,
                'price_unit': 100.0,
                'account_id': cls.account_receivable.id
            })],
            'line_ids': [(0, 0, {
                'name': 'debit',
                'account_id': cls.account_payable.id,
                'debit': 100.0,
                'credit': 0.0
            }), (0, 0, {
                'name': 'credit',
                'account_id': cls.account_receivable.id,
                'debit': 0.0,
                'credit': 100.0
            })],
            'refund_invoice_id': cls.test_refund_3.id,
        })

        


    # def setUp(self):
    #     """Set up data before each test method."""
    #     super(TestSaleOrder, self).setUp()
    #     self.periodic_report_1 = self.env['sale_order'].create({

    # def tearDown(self):
    #     """Tear down data after each test method."""
    #     super(TestSaleOrder, self).tearDown()
    #     self.periodic_report_1.unlink()

    def tearDown(self):
        """Tear down data after each test method."""
        super(TestAccountMove, self).tearDown()
        _logger.info(f'END OF "account_move" MODULE UNIT TESTS!')

# =================

    def test_x_get_is_poland(self):
        """ 
        Tests if _x_get_is_poland is correctly computed. 
        Company country should be Poland.
        """
        _logger.info(f'RUNNING "test_x_get_is_poland" TEST!')
        # if self.env.user.company_id.country_id.id == self.env.ref('base.pl').id:
        #     self.x_is_poland = True

        self.assertTrue(
            self.test_invoice_1.x_get_is_poland(),
            'Company country should be Poland.'
        )

        _logger.info(f'"test_x_get_is_poland" TEST COMPLETE!')

# =================

    def test_get_final_invoice_summary(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test_get_final_invoice_summary" TEST!')
        # self.get_final_invoice_summary(self, with_downpayments=True)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test_get_final_invoice_summary" TEST COMPLETE!')


    def test__prepare_tax_lines_data_for_totals_from_invoice(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test__prepare_tax_lines_data_for_totals_from_invoice" TEST!')
        # self._prepare_tax_lines_data_for_totals_from_invoice(self, tax_line_id_filter=None, tax_ids_filter=None)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test__prepare_tax_lines_data_for_totals_from_invoice" TEST COMPLETE!')


    def test__get_tax_totals(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test__get_tax_totals" TEST!')
        # self._get_tax_totals(self, partner, tax_lines_data, amount_total, amount_untaxed, currency)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test__get_tax_totals" TEST COMPLETE!')


    def test__x_check_correction_invoice(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test__x_check_correction_invoice" TEST!')
        # self._x_check_correction_invoice(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test__x_check_correction_invoice" TEST COMPLETE!')


    def test_clock_moving_back(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test_clock_moving_back" TEST!')
        # self.clock_moving_back(self)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test_clock_moving_back" TEST COMPLETE!')


    def test_get_connected_corrections(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test_get_connected_corrections" TEST!')
        # self.get_connected_corrections(self)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"get_connected_corrections" TEST COMPLETE!')


    def test_create(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test_create" TEST!')
        # self.create(self, vals_list)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"create" TEST COMPLETE!')


    def test_constrains_correction_data(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test_constrains_correction_data" TEST!')
        # self.constrains_correction_data(self)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"constrains_correction_data" TEST COMPLETE!')


    def test_correction_invoices_view(self):
        # ============================================= TO DO =============================================--------------------
        _logger.info(f'RUNNING "test_correction_invoices_view" TEST!')
        # self.correction_invoices_view(self)
        # _logger.info("============================ " + str())

        result = self.test_invoice_3.correction_invoices_view()
        _logger.info("============================ " + str(result))

        correct_result_1 = {
                'name': 'Correction Invoices', 
                'view_mode': 'tree,form', 
                'res_model': 'account.move', 
                'type': 'ir.actions.act_window', 
                'domain': [('id', 'in', [])]} 

        self.assertTrue(True, 'Error') 

        _logger.info(f'"correction_invoices_view" TEST COMPLETE!')


# =================

    def test_action_reverse(self):
        """ 
        Tests if action_reverse correctly changes name of correction invoice to "Credit Note". 
        """
        _logger.info(f'RUNNING "action_reverse" TEST!')
        result = self.test_invoice_1.action_reverse()
        self.assertEqual(result['name'], 
                    "Credit Note", 
                    "Wrong name of invoice, should be 'Credit Note'")
        _logger.info(f'"action_reverse" TEST COMPLETE!')

# =================







    def test_action_post(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "action_post" TEST!')
        # self.get_action_post(self)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"action_post" TEST COMPLETE!')


    def test__post(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test__post" TEST!')
        # self._post(self, soft=True)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_post" TEST COMPLETE!')


    def test__x_post_wo_validation(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "test__x_post_wo_validation" TEST!')
        # self._x_post_wo_validation(self, soft=True)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 

        _logger.info(f'"test__x_post_wo_validation" TEST COMPLETE!')

# =================

    def test__format_float(self):
        """ 
        Tests if _format_float correctly changes float number into amount number. 
        """
        _logger.info(f'RUNNING "test__format_float" TEST!')
        lang_env = self.test_invoice_1.with_context(lang='pl').env
        self.assertEqual(self.test_invoice_1._format_float(123.456, self.currency_pln_id, lang_env),
                    "123.46 zł", 
                    "Wrong format of amount, should be '123.46 zł'")
        _logger.info(f'"test__format_float" TEST COMPLETE!')

# =================


    def test_x_get_invoice_amount_summary(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "x_get_invoice_amount_summary" TEST!')
        # self.x_get_invoice_amount_summary(self)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 




        _logger.info(f'"x_get_invoice_amount_summary" TEST COMPLETE!')


    def test__reverse_move_vals(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_reverse_move_vals" TEST!')
        # self._reverse_move_vals(self, default_values, cancel=True)
        # _logger.info("============================ " + str())
        self.assertTrue(True, 'Error') 




        _logger.info(f'"_reverse_move_vals" TEST COMPLETE!')

# =================

    def test_action_reverse_pl(self):
        """ 
        Tests if action_reverse_pl correctly changes name of correction invoice to "Credit Note PL". 
        """
        _logger.info(f'RUNNING "action_reverse_pl" TEST!')
        result = self.test_invoice_1.action_reverse_pl()
        self.assertEqual(result['name'], 
                    "Credit Note PL", 
                    "Wrong name of invoice, should be 'Credit Note PL'")
        _logger.info(f'"action_reverse_pl" TEST COMPLETE!')

# =================

    def test_x_num2words_en(self):
        """ 
        Tests if x_num2words correctly changes number (amount) into text. 
        123.45 PLN in EN is "one hundred and twenty-three zlotys, forty-five groszy"
        """
        _logger.info(f'RUNNING "x_num2words" TEST!')
        _logger.info(f'* en')   
        self.assertEqual(self.test_invoice_1.x_num2words(123.45, self.currency_pln_id.name), 
                    "one hundred and twenty-three zlotys, forty-five groszy", 
                    "Wrong name o the number (123.45 in EN)")

    def test_x_num2words_pl(self):
        """ 
        Tests if x_num2words correctly changes number (amount) into text. 
        123.45 PLN in PL is "sto dwadzieścia trzy złote, czterdzieści pięć groszy"
        """
        _logger.info(f'* pl') 
        self.assertEqual(self.test_invoice_1.with_context(lang='pl').x_num2words(123.45, self.currency_pln_id.name),
                    "sto dwadzieścia trzy złote, czterdzieści pięć groszy", 
                    "Wrong name o the number (123.45 in PL)")
        _logger.info(f'"x_num2words" TEST COMPLETE!')

# =================

    def test_x_get_invoice_sign_invoice(self):
        """ 
        Tests if x_get_invoice_sign is correctly computed. 
        Sign of invoice should be 1.
        """
        _logger.info(f'RUNNING "x_get_invoice_sign" TEST!')
        _logger.info(f'* invoice')        
        self.assertEqual(self.test_invoice_1.x_get_invoice_sign(), 1, "Sign of invoice should be 1")

    def test_x_get_invoice_sign_correction_plus(self):
        """ 
        Tests if x_get_invoice_sign is correctly computed. 
        Sign of refund (plus) invoice should be 1.
        """
        _logger.info(f'* correction_plus')
        self.test_invoice_3.x_corrected_amount_total = 300.0
        self.test_refund_3.x_corrected_amount_total = 200.0
        self.assertEqual(self.test_invoice_3.x_get_invoice_sign(), 1, "Sign of refund (plus) invoice should be 1")

    def test_x_get_invoice_sign_correction_minus(self):
        """ 
        Tests if x_get_invoice_sign is correctly computed. 
        Sign of refund (minus) invoice should be -1.
        """
        _logger.info(f'* correction_minus')
        self.test_invoice_3.x_corrected_amount_total = 200.0
        self.test_refund_3.x_corrected_amount_total = 300.0
        self.assertEqual(self.test_invoice_3.x_get_invoice_sign(), -1, "Sign of refund (minus) invoice should be -1")
        _logger.info(f'"x_get_invoice_sign" TEST COMPLETE!')

# =================



        # _logger.info("============================" + str(self.test_invoice_3.refund_invoice_id))
        # _logger.info("============================" + str(self.test_invoice_3.refund_invoice_id.x_corrected_amount_total))
        # _logger.info("============================" + str(self.test_invoice_3.x_corrected_amount_total))








    def test__move_autocomplete_invoice_lines_write(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_move_autocomplete_invoice_lines_write" TEST!')
        # self._move_autocomplete_invoice_lines_write(self, vals)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_move_autocomplete_invoice_lines_write" TEST COMPLETE!')


    def test_x_update_context_with_currency_rate(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_x_update_context_with_currency_rate" TEST!')
        # self._x_update_context_with_currency_rate(self, obj=None, currency_rate=None, force=False)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_x_update_context_with_currency_rate" TEST COMPLETE!')


    def test_x_update_currency_rate(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "x_update_currency_rate" TEST!')
        # self.x_update_currency_rate(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"x_update_currency_rate" TEST COMPLETE!')


    def test__x_onchange_set_currency_rate(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_x_onchange_set_currency_rate" TEST!')
        # self._x_onchange_set_currency_rate(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_x_onchange_set_currency_rate" TEST COMPLETE!')


    def test__x_onchange_currency_rate(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_x_onchange_currency_rate" TEST!')
        # self._x_onchange_currency_rate(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_x_onchange_currency_rate" TEST COMPLETE!')


    def test__recompute_dynamic_lines(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_recompute_dynamic_lines" TEST!')
        # self._recompute_dynamic_lines(self, recompute_all_taxes=False, recompute_tax_base_amount=False)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_recompute_dynamic_lines" TEST COMPLETE!')


    def test__onchange_currency(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_onchange_currency" TEST!')
        # self._onchange_currency(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_onchange_currency" TEST COMPLETE!')


    def test_x_is_jpk_mpp(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "x_is_jpk_mpp" TEST!')
        # self.x_is_jpk_mpp(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"x_is_jpk_mpp" TEST COMPLETE!')


    def test__x_onchange_invoice_date(self):
        # ============================================= TO DO =============================================
        _logger.info(f'RUNNING "_x_onchange_invoice_date" TEST!')
        # self._x_onchange_invoice_date(self)
        self.assertTrue(True, 'Error') 

        _logger.info(f'"_x_onchange_invoice_date" TEST COMPLETE!')

