ALTER TABLE link_sessions
    ADD COLUMN IF NOT EXISTS purchase_id INTEGER;

UPDATE link_sessions AS ls
   SET purchase_id = t.purchase_id
  FROM ticket AS t
 WHERE ls.purchase_id IS NULL
   AND t.id = ls.ticket_id;
