def migrate(cr, version):
    if not version.startswith("saas~18.3."):
        return
    cr.execute(
        """
        WITH archived_contracts AS (
            SELECT c.id
                FROM hr_contract c
                JOIN hr_contract_sign_request_rel rel
                ON rel.hr_contract_id = c.id
                JOIN sign_request s
                ON s.id = rel.sign_request_id
                JOIN hr_contract_salary_offer_sign_request_rel off_rel
                ON off_rel.sign_request_id = s.id
                JOIN hr_contract_salary_offer o
                ON o.id = off_rel.hr_contract_salary_offer_id
                WHERE NOT c.active
                AND s.nb_closed = 1
                AND o.state = 'half_signed'
            GROUP BY c.id
        )
        UPDATE hr_contract c
        SET active = TRUE
        FROM archived_contracts a
        WHERE c.id = a.id
        """
    )
