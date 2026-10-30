-- ============================================================================
-- Student Drowsiness Alert System — Safe Schema Cleanup Script
-- Purpose: Safely tears down ONLY student monitoring project-owned objects without
-- affecting any unrelated tables or system objects in the Oracle schema.
-- ============================================================================

SET ECHO ON;
SET FEEDBACK ON;

PROMPT Initiating safe teardown of student monitoring objects...

-- Drop views
BEGIN
    FOR v IN (SELECT view_name FROM user_views WHERE view_name IN (
        'V_ACTIVE_ALERTS', 'V_STUDENT_INCIDENT_STATS',
        'V_SESSION_INCIDENT_REPORT', 'V_DEVICE_HEALTH_SUMMARY'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP VIEW ' || v.view_name;
    END LOOP;
END;
/

-- Drop tables in reverse foreign-key order
BEGIN
    FOR t IN (SELECT table_name FROM user_tables WHERE table_name IN (
        'AUDIT_LOG', 'ALERT_NOTIFICATIONS', 'ALERT', 'CAMERA_NODES',
        'DEVICE', 'SESSIONS', 'PROCTOR', 'EMERGENCY_CONTACT', 'STUDENT', 'USERS'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
    END LOOP;
END;
/

-- Drop sequences
BEGIN
    FOR s IN (SELECT sequence_name FROM user_sequences WHERE sequence_name IN (
        'SEQ_USERS_ID', 'SEQ_CONTACT_ID', 'SEQ_SESSIONS_ID',
        'SEQ_DEVICE_ID', 'SEQ_ALERT_ID', 'SEQ_NOTIF_ID', 'SEQ_AUDIT_ID'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP SEQUENCE ' || s.sequence_name;
    END LOOP;
END;
/

-- Drop procedures & functions
BEGIN
    EXECUTE IMMEDIATE 'DROP PROCEDURE pr_record_alert';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP PROCEDURE pr_resolve_alert';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP FUNCTION fn_calculate_risk_score';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

PROMPT Safe cleanup of student monitoring objects completed.
