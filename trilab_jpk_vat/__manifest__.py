# -*- coding: utf-8 -*-
# noinspection PyStatementEffect
{
    'name': "Trilab JPK VAT",

    'summary': """
        Generate JPK VAT XML
        """,

    'description': """
        Report and generate XML for JPK (Jednolity Plik Kontrolny) required for accounting reporting in Poland
    """,

    'author': "Trilab",
    'website': "https://trilab.pl",

    'category': 'Accounting',
    'version': '1.54',

    'depends': [
        'account_reports',
        'trilab_jpk_base',
        'trilab_invoice'
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/jpk.xml',
        'data/trilab_vat_reports.xml',
        'views/account_views.xml',
        'views/jpk_vat_7m_views.xml',
        'reports/jpk_vat_7m_pdf.xml'
    ],
    'images': [
        'static/description/banner.png'
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
    'price': 240.0,
    'currency': 'EUR'

}
