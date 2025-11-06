from odoo import fields, models, _
from odoo.exceptions import UserError, RedirectWarning

import datetime
from lxml import etree


class L10n_Nl_ReportsTaxReportHandler(models.AbstractModel):
    _name = 'l10n_nl_reports.tax.report.handler'
    _inherit = ['account.tax.report.handler']
    _description = 'Dutch Report Custom Handler'

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options['buttons'].append({'name': "XBRL", 'sequence': 30, 'action': 'open_xbrl_wizard', 'file_export_type': 'XBRL'})

    def open_xbrl_wizard(self, options):
        report = self.env['account.report'].browse(options['report_id'])
        if report.filter_multi_company != 'tax_units' and len(options['companies']) > 1:
            raise UserError(_('Please select only one company to send the report. If you wish to aggregate multiple companies, please create a tax unit.'))
        date_to = datetime.date.fromisoformat(options['date']['date_to'])
        closing_date_from, closing_date_to = self.env.ref('l10n_nl_reports.nl_tax_return_type')._get_period_boundaries(self.env.company, date_to)
        new_options = report.get_options({
            **options,
            'date': {
                'date_from': closing_date_from,
                'date_to': closing_date_to,
                'mode': 'range',
                'filter': 'custom',
            },
            'integer_rounding_enabled': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Report SBR'),
            'view_mode': 'form',
            'res_model': 'l10n_nl_reports.sbr.tax.report.wizard',
            'target': 'new',
            'context': {
                'options': new_options,
                'default_date_from': closing_date_from,
                'default_date_to': closing_date_to,
                },
            'views': [[False, 'form']],
        }

    def export_tax_report_to_xbrl(self, options):
        # This will generate the XBRL file (similar style to XML).
        report = self.env['account.report'].browse(options['report_id'])
        lines = report._get_lines(options)
        data = self._generate_codes_values(lines, options.get('codes_values'))

        date_to = fields.Date.to_date(options['date']['date_to'])
        template_xmlid = 'l10n_nl_reports.tax_report_sbr'
        if date_to.year == 2024:
            # We still need to support the NT18 taxonomy for 2024 until that declaration period is over.
            template_xmlid = 'l10n_nl_reports.tax_report_sbr_nt18'

        report_template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not report_template:
            raise RedirectWarning(
                message=_(
                    "We couldn't find the correct export template for the year %(year)s. Please upgrade your module 'Netherlands - Accounting Reports' and try again.",
                    year=date_to.year,
                ),
                action=self.env.ref('base.open_module_tree').id,
                button_text=_("Go to Apps"),
                additional_context={
                    'search_default_name': 'l10n_nl_reports',
                    'search_default_extra': True,
                },
            )

        xbrl = self.env['ir.qweb']._render(report_template.id, data)
        xbrl_element = etree.fromstring(xbrl)
        xbrl_file = etree.tostring(xbrl_element, xml_declaration=True, encoding='utf-8')
        return {
            'file_name': report.get_default_report_filename(options, 'xbrl'),
            'file_content': xbrl_file,
            'file_type': 'xml',
        }

    def _generate_codes_values(self, lines, codes_values=None):
        codes_values = codes_values or {}
        # Maps the needed taxes to their codewords used by the XBRL template.
        tax_report_lines_to_codes = {
            'l10n_nl.tax_report_rub_3c': [('InstallationDistanceSalesWithinTheEC', 'base')],
            'l10n_nl.tax_report_rub_1e': [('SuppliesServicesNotTaxed', 'base')],
            'l10n_nl.tax_report_rub_3a': [('SuppliesToCountriesOutsideTheEC', 'base')],
            'l10n_nl.tax_report_rub_3b': [('SuppliesToCountriesWithinTheEC', 'base')],
            'l10n_nl.tax_report_rub_1d': [('TaxedTurnoverPrivateUse', 'base'), ('ValueAddedTaxPrivateUse', 'tax')],
            'l10n_nl.tax_report_rub_1a': [('TaxedTurnoverSuppliesServicesGeneralTariff', 'base'), ('ValueAddedTaxSuppliesServicesGeneralTariff', 'tax')],
            'l10n_nl.tax_report_rub_1c': [('TaxedTurnoverSuppliesServicesOtherRates', 'base'), ('ValueAddedTaxSuppliesServicesOtherRates', 'tax')],
            'l10n_nl.tax_report_rub_1b': [('TaxedTurnoverSuppliesServicesReducedTariff', 'base'), ('ValueAddedTaxSuppliesServicesReducedTariff', 'tax')],
            'l10n_nl.tax_report_rub_4a': [('TurnoverFromTaxedSuppliesFromCountriesOutsideTheEC', 'base'), ('ValueAddedTaxOnSuppliesFromCountriesOutsideTheEC', 'tax')],
            'l10n_nl.tax_report_rub_4b': [('TurnoverFromTaxedSuppliesFromCountriesWithinTheEC', 'base'), ('ValueAddedTaxOnSuppliesFromCountriesWithinTheEC', 'tax')],
            'l10n_nl.tax_report_rub_2a': [('TurnoverSuppliesServicesByWhichVATTaxationIsTransferred', 'base'), ('ValueAddedTaxSuppliesServicesByWhichVATTaxationIsTransferred', 'tax')],
            'l10n_nl.tax_report_rub_btw_5b': [('ValueAddedTaxOnInput', 'tax')],
            'l10n_nl.tax_report_rub_btw_5a': [('ValueAddedTaxOwed', 'tax')],
            'l10n_nl.tax_report_rub_btw_5g': [('ValueAddedTaxOwedToBePaidBack', 'tax')],
        }
        model_trl_to_codes = {}
        for tax_report_line_id, codes in tax_report_lines_to_codes.items():
            model_trl_to_codes[self.env.ref(tax_report_line_id).id] = codes

        for line in lines:
            codes = model_trl_to_codes.get(self.env['account.report']._get_model_info_from_id(line['id'])[1]) or []
            for code, label in codes:
                codes_values[code] = str(int(next(col for col in line['columns'] if col['expression_label'] == label)['no_format']))
        return codes_values
