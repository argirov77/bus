-- Guard migration: fail deployment early when LiqPay tracking columns are missing.
DO $$
DECLARE
    missing_columns text[];
BEGIN
    SELECT array_agg(required.column_name ORDER BY required.column_name)
      INTO missing_columns
      FROM (
            VALUES
                ('liqpay_order_id'),
                ('liqpay_status'),
                ('liqpay_payment_id'),
                ('liqpay_payload')
      ) AS required(column_name)
      LEFT JOIN information_schema.columns existing
        ON existing.table_schema = 'public'
       AND existing.table_name = 'purchase'
       AND existing.column_name = required.column_name
     WHERE existing.column_name IS NULL;

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION
            'Deployment guard failed: missing purchase columns: %. Ensure migrations 018_add_liqpay_tracking.sql and 019_liqpay_payment_method_and_tracking.sql are applied.',
            array_to_string(missing_columns, ', ');
    END IF;
END
$$;
