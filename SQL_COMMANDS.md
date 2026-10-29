# AegisAlert SQL Command Reference

These examples are for the project's local SQLite database, `local_demo.db`.
Run them from the project directory:

```bash
sqlite3 local_demo.db
```

SQLite commands such as `.tables` and `.schema` are terminal commands, not SQL.
Finish a SQLite session with `.quit`.

## 1. Inspect the database

List tables:

```sql
.tables
```

Show a table's columns and constraints:

```sql
.schema Alert
.schema Student
```

Count rows:

```sql
SELECT COUNT(*) AS alert_count FROM Alert;
SELECT COUNT(*) AS student_count FROM Student;
```

## 2. Read data

Show the latest alerts:

```sql
SELECT alert_id, student_id, alert_type, severity, status, alert_time
FROM Alert
ORDER BY alert_time DESC
LIMIT 10;
```

Show alerts with student and session details:

```sql
SELECT
    a.alert_id,
    s.student_name,
    s.class_section,
    sess.subject,
    a.alert_type,
    a.severity,
    a.status,
    a.alert_time
FROM Alert AS a
JOIN Student AS s ON s.student_id = a.student_id
JOIN Sessions AS sess ON sess.session_id = a.session_id
ORDER BY a.alert_time DESC;
```

Count alerts by severity:

```sql
SELECT severity, COUNT(*) AS alert_count
FROM Alert
GROUP BY severity
ORDER BY alert_count DESC;
```

Count alerts by status:

```sql
SELECT status, COUNT(*) AS alert_count
FROM Alert
GROUP BY status
ORDER BY status;
```

Find students with more than one alert:

```sql
SELECT s.student_id, s.student_name, COUNT(*) AS alert_count
FROM Student AS s
JOIN Alert AS a ON a.student_id = s.student_id
GROUP BY s.student_id, s.student_name
HAVING COUNT(*) > 1
ORDER BY alert_count DESC;
```

Count alerts by hour (SQLite):

```sql
SELECT strftime('%H', alert_time) AS hour, COUNT(*) AS alert_count
FROM Alert
GROUP BY strftime('%H', alert_time)
ORDER BY hour;
```

Find unresolved high-risk alerts:

```sql
SELECT alert_id, student_id, severity, status, alert_time
FROM Alert
WHERE severity IN ('High', 'Critical')
  AND status <> 'Resolved'
ORDER BY alert_time DESC;
```

## 3. Update existing data

First inspect the row and confirm its ID. Then update only the intended row:

```sql
SELECT alert_id, status
FROM Alert
WHERE alert_id = 4;

UPDATE Alert
SET status = 'Acknowledged'
WHERE alert_id = 4;

SELECT alert_id, status
FROM Alert
WHERE alert_id = 4;
```

Change a student's section:

```sql
UPDATE Student
SET class_section = 'A2'
WHERE student_id = 'STU001';
```

For changes you want to review before keeping, use a transaction. Replace the
example ID with one you have checked:

```sql
BEGIN;

UPDATE Alert
SET status = 'Acknowledged'
WHERE alert_id = 4;

SELECT alert_id, status
FROM Alert
WHERE alert_id = 4;

-- Keep the change only after verifying the result:
COMMIT;

-- If the result is wrong, use ROLLBACK instead of COMMIT.
```

Always include a specific `WHERE` condition in `UPDATE` statements. Without
one, every row in the table may be changed.

## 4. Change table structure

Add a column to the existing Student table:

```sql
ALTER TABLE Student
ADD COLUMN preferred_name TEXT;
```

Create a separate table for alert notes:

```sql
CREATE TABLE Alert_Notes (
    note_id INTEGER PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    note_text TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES Alert(alert_id)
);
```

Check the result:

```sql
.schema Student
.schema Alert_Notes
```

Changing the database schema does not automatically add the field to the app.
To show or edit a new field in the frontend, update the service query, Flask
route if needed, and the relevant Jinja template. If the project is also used
with Oracle, make the equivalent Oracle schema change and support both SQL
dialects in the backend.

## 5. Backup and restore

At the SQLite prompt, make a backup before trying schema changes:

```sql
.backup local_demo_backup.db
```

To open a backup database later:

```bash
sqlite3 local_demo_backup.db
```

## Important notes

- These commands target SQLite. Oracle uses different date functions,
  parameter placeholders, and some DDL syntax.
- Direct database edits bypass the app's validation and audit logging. Use the
  app UI for normal record changes.
- Keep demo data synthetic. Avoid putting identifiable student information in
  a presentation or shared copy of this database.
- Refresh the relevant app page after a database change to see updated query
  results.
