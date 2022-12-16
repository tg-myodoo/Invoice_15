import base64
import datetime
import re

from lxml import etree

from odoo import models, fields, release, _
from odoo.exceptions import UserError
from odoo.tools import float_repr, float_round

FLAGS = [
    'GTU_01', 'GTU_02', 'GTU_03', 'GTU_04', 'GTU_05', 'GTU_06', 'GTU_07', 'GTU_08', 'GTU_09', 'GTU_10', 'GTU_11',
    'GTU_12', 'GTU_13', 'TP', 'TT_WNT', 'TT_D', 'MR_T', 'MR_UZ', 'I_42', 'I_63', 'B_SPV', 'B_SPV_DOSTAWA',
    'B_MPV_PROWIZJA', 'KorektaPodstawyOpodt', 'IMP', 'WSTO_EE', 'IED'
]

EMPTY = 'BRAK'


class JpkReportV2(models.AbstractModel):
    _name = 'account.report.jpk_vat7m_v2'
    _description = 'JPK VAT 7M 1.0E Report'
    _inherit = 'account.report.jpk_vat7m'

    @staticmethod
    def _get_query():
        return """SELECT am.id                                      AS gid, 
           jat.jpk_section                             AS JPKSection,
           p.vat                                       AS NrKontrahenta,
           p.name                                      AS NazwaKontrahenta,
           p.id                                        AS PartnerId,
           (CASE
                WHEN am.x_pl_change_jpk_proof IS NOT NULL
                    THEN am.x_pl_change_jpk_proof
                WHEN aj.type = 'sale'
                    THEN am.name
                ELSE aml.ref
               END)                                    AS DowodSprzedazyZakupu,
           am.invoice_date                             AS DataWystawienia,
           am.pl_vat_date                              AS DataSprzedazy,
           am.invoice_date                             AS DataZakupu,
           am.pl_vat_date                              AS DataWplywu,
           (CASE
                WHEN aml.tax_line_id IS NOT NULL
                    then TRUE
                ELSE FALSE
            END)                                       AS isTax,
           jat.jpk_markup                              AS JPKMarkup,
           jat.jpk_v7_group                            AS JPKGroup,
            (CASE
                WHEN jat.jpk_section='SprzedazWiersz'
                    THEN am.x_pl_vat_typ_dokumentu
                ELSE am.x_pl_vat_dokument_zakupu
            END)                                       AS TypDokumentu, 
           STRING_AGG(distinct (jpk_gtu.name), ',')               AS GTU,
           CONCAT_WS(',', CASE WHEN am.x_pl_vat_tp and jat.jpk_section='SprzedazWiersz' THEN 'TP' END,
                          CASE WHEN am.x_pl_vat_tt_wnt THEN 'TT_WNT' END,
                          CASE WHEN am.x_pl_vat_tt_d THEN 'TT_D' END,
                          CASE WHEN am.x_pl_vat_mr_t THEN 'MR_T' END,
                          CASE WHEN am.x_pl_vat_mr_uz THEN 'MR_UZ' END,
                          CASE WHEN am.x_pl_vat_i42 THEN 'I_42' END,
                          CASE WHEN am.x_pl_vat_i63 THEN 'I_63' END,
                          CASE WHEN am.x_pl_vat_b_spv THEN 'B_SPV' END,
                          CASE WHEN am.x_pl_vat_b_spv_dostawa THEN 'B_SPV_DOSTAWA' END,
                          CASE WHEN am.x_pl_vat_b_mpv_prowizja THEN 'B_MPV_PROWIZJA' END,
                          CASE WHEN am.x_pl_vat_korekta_podstawy_opodt  and jat.jpk_section='SprzedazWiersz' 
                               THEN 'KorektaPodstawyOpodt' END,
                          CASE WHEN am.x_pl_vat_imp and jat.jpk_section='ZakupWiersz' THEN 'IMP' END,
                          CASE WHEN am.x_pl_vat_wsto_ee THEN 'WSTO_EE' END,
                          CASE WHEN am.x_pl_vat_ied THEN 'IED' END
                        )                              AS Flags,
           SUM(CASE
                WHEN aml.tax_line_id IS NOT NULL and jat.jpk_section='ZakupWiersz'
                    then aml.balance
                WHEN aml.tax_line_id IS NOT NULL and jat.jpk_section='SprzedazWiersz'
                    then - aml.balance
                WHEN jat.jpk_section='SprzedazWiersz' and am.move_type in ('out_invoice', 'out_refund', 'entry')
                    then  - aml.balance
               ELSE (aml.balance)
               END)                                    AS kwota,
               am.invoice_date_due AS TerminPlatnosci
    FROM account_move AS am
             LEFT JOIN res_partner p ON am.partner_id = p.id
             LEFT JOIN account_journal aj ON am.journal_id = aj.id
             LEFT JOIN account_move_line aml ON aml.move_id = am.id
             LEFT OUTER JOIN jpk_gtu ON jpk_gtu.id = aml.x_pl_vat_gtu
             LEFT JOIN account_account_tag_account_move_line_rel aatmr ON aatmr.account_move_line_id = aml.id
             LEFT JOIN account_account_tag aat ON aat.id = aatmr.account_account_tag_id
             LEFT OUTER JOIN jpk_account_tag jat ON jat.account_tag_id = aat.id
             LEFT JOIN account_tax tax ON tax.id = aml.tax_line_id
    WHERE am.state IN %(allowed_states)s
     AND jat.jpk_document_type = %(jpk_doc_id)s
     AND aj.type IN %(journal_types)s
     AND am.pl_vat_date >= %(date_from)s
     AND am.pl_vat_date <= %(date_to)s
     AND am.company_id = %(company)s
    GROUP BY am.id, JPKSection, NrKontrahenta, NazwaKontrahenta, PartnerId, DowodSprzedazyZakupu, DataWystawienia,
             DataSprzedazy, DataZakupu, DataWplywu, isTax, TypDokumentu, Flags, JPKMarkup, JPKGroup, TerminPlatnosci
    ORDER BY JPKsection, DataWystawienia, am.id, DowodSprzedazyZakupu, JPKMarkup, JPKGroup"""

    def get_xml_extended(self, options):
        # noinspection HttpUrlsUsage
        tns = 'http://crd.gov.pl/wzor/2021/12/27/11148/'

        company = self.env.user.company_id
        jpk = etree.Element(etree.QName(tns, 'JPK'), nsmap={'tns': tns})

        header = etree.SubElement(jpk, etree.QName(tns, 'Naglowek'))

        etree.SubElement(header, etree.QName(tns, 'KodFormularza'),
                         attrib={'kodSystemowy': 'JPK_V7M (2)', 'wersjaSchemy': '1-0E'}).text = 'JPK_VAT'
        etree.SubElement(header, etree.QName(tns, 'WariantFormularza')).text = '2'
        etree.SubElement(header, etree.QName(tns, 'DataWytworzeniaJPK')).text = datetime.datetime.now().isoformat()
        etree.SubElement(header, etree.QName(tns, 'NazwaSystemu')).text = \
            "%s %s" % (release.description, release.version)
        etree.SubElement(header, etree.QName(tns, 'CelZlozenia'),
                         attrib={'poz': 'P_7'}).text = '{}'.format(options.get('cel_zlozenia', 1))

        if not company.pl_tax_office_id.code:
            raise UserError(_('PL Tax Office is not set for company {}').format(company.name))

        etree.SubElement(header, etree.QName(tns, 'KodUrzedu')).text = company.pl_tax_office_id.code

        report_date = fields.Date.to_date(options['date']['date_from'])
        etree.SubElement(header, etree.QName(tns, 'Rok')).text = str(report_date.year)
        etree.SubElement(header, etree.QName(tns, 'Miesiac')).text = str(report_date.month)

        podmiot = etree.SubElement(jpk, etree.QName(tns, 'Podmiot1'), attrib={'rola': 'Podatnik'})
        podmiot_sub = etree.SubElement(podmiot, etree.QName(tns, 'OsobaNiefizyczna'))

        try:
            etree.SubElement(podmiot_sub, etree.QName(tns, 'NIP')).text = re.sub(r'\D', '', company.vat)
        except TypeError:
            raise UserError(_("Make sure that Company's VAT number is correct"))

        etree.SubElement(podmiot_sub, etree.QName(tns, 'PelnaNazwa')).text = company.name

        # common
        if not company.email:
            raise UserError(_("Please set company email"))
        etree.SubElement(podmiot_sub, etree.QName(tns, 'Email')).text = company.email

        if company.phone:
            etree.SubElement(podmiot_sub, etree.QName(tns, 'Telefon')).text = company.phone

        deklaracja = etree.SubElement(jpk, etree.QName(tns, 'Deklaracja'))
        deklaracja_naglowek = etree.SubElement(deklaracja, etree.QName(tns, 'Naglowek'))

        etree.SubElement(deklaracja_naglowek, etree.QName(tns, 'KodFormularzaDekl'),
                         attrib={
                             'kodSystemowy': 'VAT-7 (22)',
                             'kodPodatku': 'VAT',
                             'rodzajZobowiazania': 'Z',
                             'wersjaSchemy': '1-0E'
                         }).text = 'VAT-7'

        etree.SubElement(deklaracja_naglowek, etree.QName(tns, 'WariantFormularzaDekl')).text = '22'
        pozycje_szczegolowe = etree.SubElement(deklaracja, etree.QName(tns, 'PozycjeSzczegolowe'))
        etree.SubElement(deklaracja, etree.QName(tns, 'Pouczenia')).text = '1'

        ewidencja = etree.SubElement(jpk, etree.QName(tns, 'Ewidencja'))

        ctx = self._set_context(options)

        # deactivating the prefetching saves ~35% on get_lines running time
        ctx.update({'no_format': True, 'print_mode': False, 'prefetch_fields': False, 'dict_output': True})
        # noinspection PyProtectedMember
        sections = self.with_context(ctx)._get_lines(options)

        declaration_groups = {}

        # SprzedazWiersz
        section_count = 0
        section_sum = 0.0

        for line in sections.get('SprzedazWiersz', []):
            section_count += 1
            sale_row = etree.SubElement(ewidencja, etree.QName(tns, 'SprzedazWiersz'))
            etree.SubElement(sale_row, etree.QName(tns, 'LpSprzedazy')).text = str(line['counter'])

            _vat = line['data']['nrkontrahenta']
            _country = None
            _flags = set(line['data']['flags'].split(',')) if line['data']['flags'] else set()
            _taxes = set()

            if line['data']['partnerid']:
                _country = self.env['res.partner'].browse(line['data']['partnerid']).x_get_tin_country()

            if _country:
                etree.SubElement(sale_row, etree.QName(tns, 'KodKrajuNadaniaTIN')).text = _country

            etree.SubElement(sale_row, etree.QName(tns, 'NrKontrahenta')).text = _vat or EMPTY
            etree.SubElement(sale_row, etree.QName(tns, 'NazwaKontrahenta')).text = \
                line['data']['nazwakontrahenta'] or EMPTY
            etree.SubElement(sale_row, etree.QName(tns, 'DowodSprzedazy')).text = line['data']['dowodsprzedazyzakupu']
            etree.SubElement(sale_row, etree.QName(tns, 'DataWystawienia')).text = \
                line['data']['datawystawienia'].isoformat()

            if line['data']['datasprzedazy'] and line['data']['datawystawienia'] \
                    and line['data']['datasprzedazy'] != line['data']['datawystawienia']:
                etree.SubElement(sale_row, etree.QName(tns, 'DataSprzedazy')).text = \
                    line['data']['datasprzedazy'].isoformat()

            if line['data']['typdokumentu']:
                etree.SubElement(sale_row, etree.QName(tns, 'TypDokumentu')).text = line['data']['typdokumentu']

            for child in line['children']:
                if child['istax']:
                    section_sum += child['kwota']

                if child['gtu']:
                    _flags.add(child['gtu'])

                if child['jpkgroup']:
                    declaration_groups.setdefault(child['jpkgroup'], 0.0)
                    declaration_groups[child['jpkgroup']] += child['kwota']

                _taxes.add((child['jpkmarkup'], child['kwota']))

            for flag in filter(lambda f: f in _flags, FLAGS):
                etree.SubElement(sale_row, etree.QName(tns, flag)).text = '1'
                if flag == 'KorektaPodstawyOpodt' and line['data']['terminplatnosci']:
                    etree.SubElement(sale_row, etree.QName(tns, 'TerminPlatnosci')).text = \
                        line['data']['terminplatnosci'].isoformat()

            for tag, value in sorted(_taxes, key=lambda x: x[0]):
                etree.SubElement(sale_row, etree.QName(tns, tag)).text = float_repr(value, 2)

        section = etree.SubElement(ewidencja, etree.QName(tns, 'SprzedazCtrl'))
        etree.SubElement(section, etree.QName(tns, 'LiczbaWierszySprzedazy')).text = '{:d}'.format(section_count)
        etree.SubElement(section, etree.QName(tns, 'PodatekNalezny')).text = '{:.2f}'.format(section_sum)

        # ZakupWiersz
        section_count = 0
        section_sum = 0.0

        for line in sections.get('ZakupWiersz', []):
            section_count += 1
            purchase_row = etree.SubElement(ewidencja, etree.QName(tns, 'ZakupWiersz'))
            etree.SubElement(purchase_row, etree.QName(tns, 'LpZakupu')).text = str(line['counter'])

            _vat = line['data']['nrkontrahenta']
            _country = None
            _flags = set(line['data']['flags'].split(',')) if line['data']['flags'] else set()
            _taxes = set()

            if line['data']['partnerid']:
                _country = self.env['res.partner'].browse(line['data']['partnerid']).x_get_tin_country()

            if _country:
                etree.SubElement(purchase_row, etree.QName(tns, 'KodKrajuNadaniaTIN')).text = _country

            etree.SubElement(purchase_row, etree.QName(tns, 'NrDostawcy')).text = _vat or EMPTY

            etree.SubElement(purchase_row, etree.QName(tns, 'NazwaDostawcy')).text = \
                line['data']['nazwakontrahenta'] or EMPTY
            etree.SubElement(purchase_row, etree.QName(tns, 'DowodZakupu')).text = line['data']['dowodsprzedazyzakupu']

            etree.SubElement(purchase_row, etree.QName(tns, 'DataZakupu')).text = line['data']['datazakupu'].isoformat()

            if line['data']['datawplywu'] and line['data']['datazakupu'] \
                    and line['data']['datawplywu'] != line['data']['datazakupu']:
                etree.SubElement(purchase_row, etree.QName(tns, 'DataWplywu')).text = \
                    line['data']['datawplywu'].isoformat()

            if line['data']['typdokumentu']:
                etree.SubElement(purchase_row, etree.QName(tns, 'DokumentZakupu')).text = line['data']['typdokumentu']

            for child in line['children']:
                if child['istax']:
                    section_sum += child['kwota']
                if child['gtu']:
                    _flags.add(child['gtu'])

                if child['jpkgroup']:
                    declaration_groups.setdefault(child['jpkgroup'], 0.0)
                    declaration_groups[child['jpkgroup']] += child['kwota']

                _taxes.add((child['jpkmarkup'], child['kwota']))

            for flag in filter(lambda f: f in _flags, FLAGS):
                etree.SubElement(purchase_row, etree.QName(tns, flag)).text = '1'

            for tag, value in sorted(_taxes, key=lambda x: x[0]):
                etree.SubElement(purchase_row, etree.QName(tns, tag)).text = float_repr(value, 2)

        section = etree.SubElement(ewidencja, etree.QName(tns, 'ZakupCtrl'))
        etree.SubElement(section, etree.QName(tns, 'LiczbaWierszyZakupow')).text = '{:d}'.format(section_count)
        etree.SubElement(section, etree.QName(tns, 'PodatekNaliczony')).text = '{:.2f}'.format(section_sum)

        for tag, amount in declaration_groups.items():
            int_amount = declaration_groups[tag] = int(float_round(amount, 0))
            etree.SubElement(pozycje_szczegolowe, etree.QName(tns, tag.upper())).text = str(int_amount)

        return etree.tostring(jpk, encoding='UTF-8', xml_declaration=True, pretty_print=True), declaration_groups

    def export_xml(self, options):
        report_date = fields.Date.to_date(options['date']['date_from'])

        xml, sums = self.get_xml_extended(options)
        sums = {k.lower(): v for k, v in sums.items()}

        v7m_report = self.env['jpk.vat.7m'].create({
            'version': '1-0E',
            'year': report_date.year,
            'month': report_date.month,
            'cel_zlozenia': options.get('cel_zlozenia', 1),
            'source_xml': base64.b64encode(xml),
            **sums
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'jpk.vat.7m',
            'views': [[False, 'form']],
            'name': 'JPK VAT 7M',
            'res_id': v7m_report.id,
            'target': 'new',
        }
