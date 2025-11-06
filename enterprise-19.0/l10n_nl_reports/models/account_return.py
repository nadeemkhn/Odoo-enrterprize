from dateutil.relativedelta import relativedelta

from odoo import api, models, _


class AccountReturn(models.Model):
    _inherit = 'account.return'

    @api.model
    def _evaluate_deadline(self, company, return_type, return_type_external_id, date_from, date_to):
        if return_type_external_id == 'l10n_nl_reports.nl_tax_return_type' and not return_type.deadline_days_delay:
            return date_to + relativedelta(months=1)

        return super()._evaluate_deadline(company, return_type, return_type_external_id, date_from, date_to)

    def _get_pay_wizard(self):
        if self.type_id == self.env.ref('l10n_nl_reports.nl_tax_return_type'):
            vat_pay_wizard = self.env['l10n_nl_reports.vat.pay.wizard'].create({
                'company_id': self.company_id.id,
                'partner_bank_id': self.type_id.payment_partner_bank_id.id,
                'currency_id': self.amount_to_pay_currency_id.id,
                'amount_to_pay': self.total_amount_to_pay,
                'return_id': self.id,
            })

            return {
                'type': 'ir.actions.act_window',
                'name': _("VAT Payment"),
                'res_model': 'l10n_nl_reports.vat.pay.wizard',
                'res_id': vat_pay_wizard.id,
                'views': [(False, 'form')],
                'target': 'new',
            }

        return super()._get_pay_wizard()

    def _postprocess_vat_closing_entry_results(self, company, options, results):
        # OVERRIDE
        """ Apply the rounding from the Dutch tax report by adding a line to the end of the query results
            representing the sum of the roundings on each line of the tax report.
        """
        if self.type_external_id == 'l10n_nl_reports.nl_tax_return_type':
            rounding_accounts = {
                'profit': company.l10n_nl_rounding_difference_profit_account_id,
                'loss': company.l10n_nl_rounding_difference_loss_account_id,
            }

            vat_results_summary = [
                ('total', self.env.ref('l10n_nl.tax_report_rub_btw_5g').id, 'tax'),
            ]

            return self._vat_closing_entry_results_rounding(company, options, results, rounding_accounts, vat_results_summary)

        return super()._postprocess_vat_closing_entry_results(company, options, results)
