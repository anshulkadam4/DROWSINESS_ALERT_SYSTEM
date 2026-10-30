-- ============================================================================
-- Student Drowsiness Alert System
-- Enterprise Oracle Database 21c XE / Free Setup Script
-- Relational database schema and sample data
-- Author: Anshul Suhas Kadam (Reg No: 25BCE2117)
-- ============================================================================
-- Compatible with Oracle Database 21c Express Edition (XEPDB1)
-- and Oracle Database 23c Free (FREEPDB1).
-- Run this script using SQL*Plus, SQLcl, or Oracle SQL Developer:
--   SQL> @schema_oracle.sql
-- ============================================================================

SET ECHO ON;
SET FEEDBACK ON;
WHENEVER SQLERROR CONTINUE;

-- ----------------------------------------------------------------------------
-- 1. SAFE CLEANUP OF PROJECT-OWNED OBJECTS ONLY
-- ----------------------------------------------------------------------------
PROMPT Cleaning up existing student monitoring database objects...

BEGIN
    FOR t IN (SELECT table_name FROM user_tables WHERE table_name IN (
        'AUDIT_LOG', 'ALERT_NOTIFICATIONS', 'ALERT', 'CAMERA_NODES',
        'DEVICE', 'SESSIONS', 'PROCTOR', 'EMERGENCY_CONTACT', 'STUDENT', 'USERS'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
    END LOOP;
END;
/

BEGIN
    FOR v IN (SELECT view_name FROM user_views WHERE view_name IN (
        'V_ACTIVE_ALERTS', 'V_STUDENT_INCIDENT_STATS',
        'V_SESSION_INCIDENT_REPORT', 'V_DEVICE_HEALTH_SUMMARY'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP VIEW ' || v.view_name;
    END LOOP;
END;
/

BEGIN
    FOR s IN (SELECT sequence_name FROM user_sequences WHERE sequence_name IN (
        'SEQ_USERS_ID', 'SEQ_CONTACT_ID', 'SEQ_SESSIONS_ID',
        'SEQ_DEVICE_ID', 'SEQ_ALERT_ID', 'SEQ_NOTIF_ID', 'SEQ_AUDIT_ID'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP SEQUENCE ' || s.sequence_name;
    END LOOP;
END;
/

PROMPT Cleanup completed successfully.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK;

-- ----------------------------------------------------------------------------
-- 2. SEQUENCES FOR PRIMARY KEYS
-- ----------------------------------------------------------------------------
CREATE SEQUENCE SEQ_USERS_ID   START WITH 10 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_CONTACT_ID START WITH 10 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_SESSIONS_ID START WITH 10 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_DEVICE_ID  START WITH 10 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_ALERT_ID   START WITH 100 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_NOTIF_ID   START WITH 10 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE SEQ_AUDIT_ID   START WITH 100 INCREMENT BY 1 NOCACHE;

-- ----------------------------------------------------------------------------
-- 3. CORE RELATIONAL TABLES (3rd Normal Form & Constraints)
-- ----------------------------------------------------------------------------

-- Table: USERS (Authentication & Role-Based Access Control)
CREATE TABLE Users (
    user_id       NUMBER PRIMARY KEY,
    username      VARCHAR2(50) NOT NULL UNIQUE,
    password_hash VARCHAR2(255) NOT NULL,
    full_name     VARCHAR2(100) NOT NULL,
    role          VARCHAR2(20) DEFAULT 'Faculty' CHECK (role IN ('Administrator', 'Faculty')),
    email         VARCHAR2(100) NOT NULL UNIQUE,
    created_at    DATE DEFAULT SYSDATE
);

-- Table: STUDENT (Student Demographics & Academic Track)
CREATE TABLE Student (
    student_id       VARCHAR2(15) PRIMARY KEY,
    student_name     VARCHAR2(50) NOT NULL,
    class_section    VARCHAR2(10) NOT NULL,
    email            VARCHAR2(60) NOT NULL UNIQUE,
    enrollment_year  NUMBER CHECK (enrollment_year BETWEEN 2020 AND 2030),
    department       VARCHAR2(50) DEFAULT 'CSE'
);

-- Table: EMERGENCY_CONTACT (Parent / Guardian Contact Reference)
CREATE TABLE Emergency_Contact (
    contact_id     NUMBER PRIMARY KEY,
    student_id     VARCHAR2(15) NOT NULL,
    contact_name   VARCHAR2(60) NOT NULL,
    relationship   VARCHAR2(30),
    phone_number   VARCHAR2(20) NOT NULL,
    email          VARCHAR2(60),
    CONSTRAINT fk_contact_student FOREIGN KEY (student_id)
        REFERENCES Student(student_id) ON DELETE CASCADE
);

-- Table: PROCTOR (Invigilators & Teaching Assistants)
CREATE TABLE Proctor (
    proctor_id     VARCHAR2(15) PRIMARY KEY,
    proctor_name   VARCHAR2(60) NOT NULL,
    department     VARCHAR2(50),
    email          VARCHAR2(60) UNIQUE,
    phone          VARCHAR2(20),
    assigned_room  VARCHAR2(30)
);

-- Table: SESSIONS (Academic Lecture & Laboratory Time-Blocks)
CREATE TABLE Sessions (
    session_id       NUMBER PRIMARY KEY,
    session_date     DATE NOT NULL,
    subject          VARCHAR2(40) NOT NULL,
    faculty_name     VARCHAR2(60) NOT NULL,
    duration_minutes NUMBER CHECK (duration_minutes > 0),
    class_section    VARCHAR2(10) NOT NULL,
    proctor_id       VARCHAR2(15),
    CONSTRAINT fk_session_proctor FOREIGN KEY (proctor_id)
        REFERENCES Proctor(proctor_id) ON DELETE SET NULL
);

-- Table: DEVICE (Sensors & Cameras Capturing Telemetry)
CREATE TABLE Device (
    device_id    NUMBER PRIMARY KEY,
    device_type  VARCHAR2(30) CHECK (device_type IN ('Camera', 'IR Sensor', 'Accelerometer', 'Eye Tracker')),
    location     VARCHAR2(50) NOT NULL,
    install_date DATE DEFAULT SYSDATE,
    status       VARCHAR2(15) DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive', 'Maintenance')),
    health_score NUMBER DEFAULT 98 CHECK (health_score BETWEEN 0 AND 100)
);

-- Table: CAMERA_NODES (Detailed Sensor Telemetry Endpoints)
CREATE TABLE Camera_Nodes (
    node_id          VARCHAR2(20) PRIMARY KEY,
    device_id        NUMBER NOT NULL,
    ip_address       VARCHAR2(30),
    resolution       VARCHAR2(20) DEFAULT '1080p',
    frame_rate       NUMBER DEFAULT 30,
    firmware_version VARCHAR2(20) DEFAULT 'v2.4.1',
    stream_status    VARCHAR2(20) DEFAULT 'Online' CHECK (stream_status IN ('Online', 'Degraded', 'Offline')),
    CONSTRAINT fk_node_device FOREIGN KEY (device_id)
        REFERENCES Device(device_id) ON DELETE CASCADE
);

-- Table: ALERT (Central Drowsiness & Negligence Event Repository)
CREATE TABLE Alert (
    alert_id         NUMBER PRIMARY KEY,
    student_id       VARCHAR2(15) NOT NULL,
    session_id       NUMBER NOT NULL,
    device_id        NUMBER NOT NULL,
    alert_type       VARCHAR2(20) CHECK (alert_type IN ('Drowsiness', 'Negligence', 'Distraction', 'Absence')),
    alert_time       DATE NOT NULL,
    severity         VARCHAR2(10) DEFAULT 'Medium' CHECK (severity IN ('Low', 'Medium', 'High', 'Critical')),
    status           VARCHAR2(15) DEFAULT 'Pending' CHECK (status IN ('Pending', 'Acknowledged', 'Resolved')),
    eye_closure_sec  NUMBER(4,1) DEFAULT 0.0,
    resolution_notes VARCHAR2(255),
    resolved_by      VARCHAR2(50),
    resolved_at      DATE,
    CONSTRAINT fk_alert_student FOREIGN KEY (student_id) REFERENCES Student(student_id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_session FOREIGN KEY (session_id) REFERENCES Sessions(session_id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_device  FOREIGN KEY (device_id)  REFERENCES Device(device_id)  ON DELETE CASCADE
);

-- Table: ALERT_NOTIFICATIONS (Dispatched Email and SMS Log)
CREATE TABLE Alert_Notifications (
    notification_id NUMBER PRIMARY KEY,
    alert_id        NUMBER NOT NULL,
    recipient       VARCHAR2(100) NOT NULL,
    channel         VARCHAR2(10) CHECK (channel IN ('Email', 'SMS')),
    sent_time       DATE DEFAULT SYSDATE,
    status          VARCHAR2(15) DEFAULT 'Simulated' CHECK (status IN ('Delivered', 'Simulated', 'Failed')),
    message_text    VARCHAR2(300) NOT NULL,
    CONSTRAINT fk_notif_alert FOREIGN KEY (alert_id) REFERENCES Alert(alert_id) ON DELETE CASCADE
);

-- Table: AUDIT_LOG (Immutable Activity & Change History)
CREATE TABLE Audit_Log (
    audit_id     NUMBER PRIMARY KEY,
    action_type  VARCHAR2(30) NOT NULL,
    table_name   VARCHAR2(30) NOT NULL,
    record_id    VARCHAR2(50) NOT NULL,
    performed_by VARCHAR2(50) NOT NULL,
    action_time  DATE DEFAULT SYSDATE,
    details      VARCHAR2(500)
);

-- ----------------------------------------------------------------------------
-- 4. PERFORMANCE INDEXES
-- ----------------------------------------------------------------------------
CREATE INDEX idx_alert_student_time ON Alert(student_id, alert_time);
CREATE INDEX idx_alert_session ON Alert(session_id);
CREATE INDEX idx_alert_device ON Alert(device_id);
CREATE INDEX idx_alert_status_sev ON Alert(status, severity);
CREATE INDEX idx_notif_alert ON Alert_Notifications(alert_id);
CREATE INDEX idx_audit_time ON Audit_Log(action_time);

-- ----------------------------------------------------------------------------
-- 5. RELATIONAL VIEWS FOR REPORTING & ANALYTICS
-- ----------------------------------------------------------------------------

-- View 1: Active & Unresolved Incident Summary
CREATE OR REPLACE VIEW v_active_alerts AS
SELECT
    a.alert_id,
    a.student_id,
    s.student_name,
    s.class_section,
    s.department,
    a.session_id,
    sess.subject,
    sess.faculty_name,
    a.device_id,
    d.device_type,
    d.location,
    a.alert_type,
    a.severity,
    a.status,
    a.eye_closure_sec,
    TO_CHAR(a.alert_time, 'YYYY-MM-DD HH24:MI:SS') AS alert_time_str,
    a.resolution_notes,
    a.resolved_by,
    TO_CHAR(a.resolved_at, 'YYYY-MM-DD HH24:MI') AS resolved_at_str
FROM Alert a
JOIN Student s ON a.student_id = s.student_id
JOIN Sessions sess ON a.session_id = sess.session_id
JOIN Device d ON a.device_id = d.device_id;

-- View 2: Student Risk Profiling
CREATE OR REPLACE VIEW v_student_incident_stats AS
SELECT
    s.student_id,
    s.student_name,
    s.class_section,
    s.department,
    COUNT(a.alert_id) AS total_incidents,
    SUM(CASE WHEN a.severity IN ('High', 'Critical') THEN 1 ELSE 0 END) AS high_risk_count,
    SUM(CASE WHEN a.status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,
    ROUND(AVG(NVL(a.eye_closure_sec, 0)), 1) AS avg_closure_sec,
    MAX(a.alert_time) AS last_incident_time
FROM Student s
LEFT JOIN Alert a ON s.student_id = a.student_id
GROUP BY s.student_id, s.student_name, s.class_section, s.department;

-- View 3: Session Health & Incident Analysis
CREATE OR REPLACE VIEW v_session_incident_report AS
SELECT
    sess.session_id,
    sess.session_date,
    sess.subject,
    sess.faculty_name,
    sess.class_section,
    COUNT(a.alert_id) AS incident_count,
    SUM(CASE WHEN a.alert_type = 'Drowsiness' THEN 1 ELSE 0 END) AS drowsiness_count,
    SUM(CASE WHEN a.alert_type = 'Negligence' THEN 1 ELSE 0 END) AS negligence_count,
    SUM(CASE WHEN a.severity = 'High' THEN 1 ELSE 0 END) AS high_severity_count
FROM Sessions sess
LEFT JOIN Alert a ON sess.session_id = a.session_id
GROUP BY sess.session_id, sess.session_date, sess.subject, sess.faculty_name, sess.class_section;

-- View 4: Device Reliability & Node Summary
CREATE OR REPLACE VIEW v_device_health_summary AS
SELECT
    d.device_id,
    d.device_type,
    d.location,
    d.status,
    d.health_score,
    COUNT(DISTINCT c.node_id) AS node_count,
    COUNT(DISTINCT a.alert_id) AS total_alerts_recorded
FROM Device d
LEFT JOIN Camera_Nodes c ON d.device_id = c.device_id
LEFT JOIN Alert a ON d.device_id = a.device_id
GROUP BY d.device_id, d.device_type, d.location, d.status, d.health_score;

-- ----------------------------------------------------------------------------
-- 6. STORED PROCEDURES & FUNCTIONS
-- ----------------------------------------------------------------------------

-- Procedure: Record New Alert with Repeat Incident Verification
CREATE OR REPLACE PROCEDURE pr_record_alert (
    p_alert_id     IN NUMBER,
    p_student_id   IN VARCHAR2,
    p_session_id   IN NUMBER,
    p_device_id    IN NUMBER,
    p_alert_type   IN VARCHAR2,
    p_severity     IN VARCHAR2,
    p_eye_sec      IN NUMBER,
    p_performed_by IN VARCHAR2,
    o_status       OUT VARCHAR2
) AS
    v_recent_count NUMBER;
    v_student_mail VARCHAR2(60);
    v_student_name VARCHAR2(50);
BEGIN
    -- 1. Insert Alert record
    INSERT INTO Alert (
        alert_id, student_id, session_id, device_id,
        alert_type, alert_time, severity, status, eye_closure_sec
    ) VALUES (
        p_alert_id, p_student_id, p_session_id, p_device_id,
        p_alert_type, SYSDATE, p_severity, 'Pending', NVL(p_eye_sec, 0.0)
    );

    -- 2. Check for repeated alert pattern in same session
    SELECT COUNT(*) INTO v_recent_count
    FROM Alert
    WHERE student_id = p_student_id
      AND session_id = p_session_id
      AND alert_id != p_alert_id;

    -- 3. Retrieve student email for notification simulation
    SELECT email, student_name INTO v_student_mail, v_student_name
    FROM Student WHERE student_id = p_student_id;

    -- 4. Dispatch simulated email notification
    INSERT INTO Alert_Notifications (
        notification_id, alert_id, recipient, channel, sent_time, status, message_text
    ) VALUES (
        SEQ_NOTIF_ID.NEXTVAL,
        p_alert_id,
        v_student_mail,
        'Email',
        SYSDATE,
        'Simulated',
        'Student Drowsiness Alert System: ' || p_alert_type || ' (' || p_severity || ' risk) logged for ' || v_student_name || '.'
    );

    -- 5. Record in Audit Log
    INSERT INTO Audit_Log (
        audit_id, action_type, table_name, record_id, performed_by, action_time, details
    ) VALUES (
        SEQ_AUDIT_ID.NEXTVAL,
        'CREATE',
        'Alert',
        TO_CHAR(p_alert_id),
        p_performed_by,
        SYSDATE,
        'Logged ' || p_alert_type || ' incident for ' || p_student_id || ' (Prior session events: ' || v_recent_count || ')'
    );

    COMMIT;
    o_status := 'SUCCESS: Alert recorded successfully with simulated dispatch.';
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        o_status := 'ERROR: ' || SQLERRM;
END pr_record_alert;
/

-- Procedure: Acknowledge & Resolve Alert Workflow
CREATE OR REPLACE PROCEDURE pr_resolve_alert (
    p_alert_id     IN NUMBER,
    p_new_status   IN VARCHAR2,
    p_notes        IN VARCHAR2,
    p_resolved_by  IN VARCHAR2,
    o_result       OUT VARCHAR2
) AS
BEGIN
    UPDATE Alert
    SET status = p_new_status,
        resolution_notes = p_notes,
        resolved_by = p_resolved_by,
        resolved_at = SYSDATE
    WHERE alert_id = p_alert_id;

    IF SQL%ROWCOUNT = 0 THEN
        o_result := 'NOT_FOUND: Alert #' || p_alert_id || ' does not exist.';
        RETURN;
    END IF;

    INSERT INTO Audit_Log (
        audit_id, action_type, table_name, record_id, performed_by, action_time, details
    ) VALUES (
        SEQ_AUDIT_ID.NEXTVAL,
        UPPER(p_new_status),
        'Alert',
        TO_CHAR(p_alert_id),
        p_resolved_by,
        SYSDATE,
        'Status updated to ' || p_new_status || '. Notes: ' || NVL(p_notes, 'None provided')
    );

    COMMIT;
    o_result := 'SUCCESS: Alert #' || p_alert_id || ' updated to ' || p_new_status;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        o_result := 'ERROR: ' || SQLERRM;
END pr_resolve_alert;
/

-- Function: Compute Student Risk Index (0 - 100)
CREATE OR REPLACE FUNCTION fn_calculate_risk_score (
    p_student_id IN VARCHAR2
) RETURN NUMBER IS
    v_total_alerts NUMBER := 0;
    v_high_alerts  NUMBER := 0;
    v_score        NUMBER := 0;
BEGIN
    SELECT COUNT(*),
           SUM(CASE WHEN severity IN ('High', 'Critical') THEN 1 ELSE 0 END)
    INTO v_total_alerts, v_high_alerts
    FROM Alert
    WHERE student_id = p_student_id;

    IF v_total_alerts = 0 THEN
        RETURN 0;
    END IF;

    -- Weighted formula: each standard alert = 10 pts, each high alert = 25 pts (capped at 100)
    v_score := (v_total_alerts * 10) + (NVL(v_high_alerts, 0) * 15);
    IF v_score > 100 THEN
        v_score := 100;
    END IF;

    RETURN v_score;
END fn_calculate_risk_score;
/

-- ----------------------------------------------------------------------------
-- 7. AUDIT TRIGGERS
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TRIGGER trg_alert_audit_insert
AFTER INSERT ON Alert
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Log (
        audit_id, action_type, table_name, record_id, performed_by, action_time, details
    ) VALUES (
        SEQ_AUDIT_ID.NEXTVAL,
        'INSERT_TRIGGER',
        'Alert',
        TO_CHAR(:NEW.alert_id),
        'SYSTEM_TRIGGER',
        SYSDATE,
        'Auto-audited creation of ' || :NEW.alert_type || ' (' || :NEW.severity || ') for student ' || :NEW.student_id
    );
END;
/

-- ----------------------------------------------------------------------------
-- 8. SAMPLE DATA
-- ----------------------------------------------------------------------------
PROMPT Seeding default administrative and faculty accounts...
-- Passwords: admin -> admin123, faculty -> faculty123
INSERT INTO Users VALUES (1, 'admin', 'pbkdf2:sha256:600000$tJ9P0v2x$58b3c1ec252f9547d698e4f553f18e998797e55ce91ad05d0e2e92cbb4d99411', 'Chief Invigilator (Admin)', 'Administrator', 'admin@example.com', SYSDATE);
INSERT INTO Users VALUES (2, 'faculty', 'pbkdf2:sha256:600000$rT2W8v7x$49a1d2ec141f8436c587d3e442e07d887686d44bd80ac04c0d1d81baa3c88302', 'Faculty Demo', 'Faculty', 'faculty@example.com', SYSDATE);

PROMPT Seeding sample students...
INSERT INTO Student VALUES ('STU001', 'Alex Morgan', 'A1', 'student1@example.com', 2025, 'CSE');
INSERT INTO Student VALUES ('STU002', 'Taylor Reed', 'A1', 'student2@example.com', 2025, 'CSE');
INSERT INTO Student VALUES ('STU003', 'Jordan Lee', 'B2', 'student3@example.com', 2025, 'Data Science');
INSERT INTO Student VALUES ('STU004', 'Casey Quinn', 'B2', 'student4@example.com', 2025, 'Cyber Security');
INSERT INTO Student VALUES ('STU005', 'Riley Chen', 'A1', 'student5@example.com', 2025, 'CSE');
INSERT INTO Student VALUES ('STU006', 'Sam Patel', 'B1', 'student6@example.com', 2025, 'CSE');
INSERT INTO Student VALUES ('STU007', 'Morgan Shah', 'A2', 'student7@example.com', 2025, 'Information Tech');

PROMPT Seeding Emergency Contacts...
INSERT INTO Emergency_Contact VALUES (1, 'STU001', 'Guardian One', 'Parent', '000-000-0001', 'guardian1@example.com');
INSERT INTO Emergency_Contact VALUES (2, 'STU002', 'Guardian Two', 'Parent', '000-000-0002', 'guardian2@example.com');
INSERT INTO Emergency_Contact VALUES (3, 'STU003', 'Guardian Three', 'Guardian', '000-000-0003', 'guardian3@example.com');
INSERT INTO Emergency_Contact VALUES (4, 'STU004', 'Guardian Four', 'Parent', '000-000-0004', 'guardian4@example.com');

PROMPT Seeding Proctors...
INSERT INTO Proctor VALUES ('PR-101', 'Faculty One', 'CSE Dept', 'faculty1@example.com', '000-000-0101', 'PRP353');
INSERT INTO Proctor VALUES ('PR-102', 'Faculty Two', 'CSE Dept', 'faculty2@example.com', '000-000-0102', 'SJT101');
INSERT INTO Proctor VALUES ('PR-103', 'Faculty Three', 'Data Science Dept', 'faculty3@example.com', '000-000-0103', 'TT205');

PROMPT Seeding Sessions...
INSERT INTO Sessions VALUES (1, TO_DATE('2026-08-10','YYYY-MM-DD'), 'DBMS Lab', 'Faculty One', 50, 'A1', 'PR-101');
INSERT INTO Sessions VALUES (2, TO_DATE('2026-08-12','YYYY-MM-DD'), 'Data Structures', 'Faculty Two', 60, 'A1', 'PR-102');
INSERT INTO Sessions VALUES (3, TO_DATE('2026-08-14','YYYY-MM-DD'), 'Networks', 'Faculty Three', 45, 'B2', 'PR-103');
INSERT INTO Sessions VALUES (4, TO_DATE('2026-08-15','YYYY-MM-DD'), 'Operating Systems', 'Faculty One', 60, 'A1', 'PR-101');
INSERT INTO Sessions VALUES (5, TO_DATE('2026-08-16','YYYY-MM-DD'), 'Software Engineering', 'Faculty Two', 50, 'B1', 'PR-102');

PROMPT Seeding Devices...
INSERT INTO Device VALUES (1, 'Camera', 'PRP353', TO_DATE('2026-01-01','YYYY-MM-DD'), 'Active', 99);
INSERT INTO Device VALUES (2, 'IR Sensor', 'PRP353', TO_DATE('2026-01-01','YYYY-MM-DD'), 'Active', 96);
INSERT INTO Device VALUES (3, 'Accelerometer', 'SJT101', TO_DATE('2026-01-05','YYYY-MM-DD'), 'Inactive', 75);
INSERT INTO Device VALUES (4, 'Eye Tracker', 'TT205', TO_DATE('2026-02-10','YYYY-MM-DD'), 'Active', 100);
INSERT INTO Device VALUES (5, 'Camera', 'SJT101', TO_DATE('2026-02-15','YYYY-MM-DD'), 'Active', 92);

PROMPT Seeding Camera Nodes...
INSERT INTO Camera_Nodes VALUES ('NODE-CAM-01', 1, '192.168.10.101', '4K UltraHD', 60, 'v3.1.2', 'Online');
INSERT INTO Camera_Nodes VALUES ('NODE-IR-01', 2, '192.168.10.102', 'N/A (IR Array)', 100, 'v1.8.0', 'Online');
INSERT INTO Camera_Nodes VALUES ('NODE-ACC-01', 3, '192.168.10.103', 'N/A (MEMS)', 50, 'v1.4.1', 'Offline');
INSERT INTO Camera_Nodes VALUES ('NODE-EYE-01', 4, '192.168.10.104', '1080p IR 120Hz', 120, 'v2.9.0', 'Online');
INSERT INTO Camera_Nodes VALUES ('NODE-CAM-02', 5, '192.168.10.105', '1080p HD', 30, 'v2.4.0', 'Online');

PROMPT Seeding sample alerts...
INSERT INTO Alert VALUES (1, 'STU001', 1, 1, 'Drowsiness', TO_DATE('2026-08-10 09:15','YYYY-MM-DD HH24:MI'), 'High', 'Resolved', 4.8, 'Student informed after lab; advised rest before morning class.', 'Faculty One', TO_DATE('2026-08-10 11:30','YYYY-MM-DD HH24:MI'));
INSERT INTO Alert VALUES (2, 'STU002', 1, 2, 'Negligence', TO_DATE('2026-08-10 09:20','YYYY-MM-DD HH24:MI'), 'Medium', 'Acknowledged', 0.0, 'Observed secondary phone screen under desk.', 'Faculty One', TO_DATE('2026-08-10 09:35','YYYY-MM-DD HH24:MI'));
INSERT INTO Alert VALUES (3, 'STU003', 2, 1, 'Drowsiness', TO_DATE('2026-08-12 10:05','YYYY-MM-DD HH24:MI'), 'Low', 'Resolved', 2.3, 'Brief fatigue event during lecture; recovered quickly.', 'Faculty Two', TO_DATE('2026-08-12 10:45','YYYY-MM-DD HH24:MI'));
INSERT INTO Alert VALUES (4, 'STU001', 2, 2, 'Drowsiness', TO_DATE('2026-08-12 10:10','YYYY-MM-DD HH24:MI'), 'High', 'Pending', 5.1, NULL, NULL, NULL);
INSERT INTO Alert VALUES (5, 'STU001', 2, 1, 'Negligence', TO_DATE('2026-08-12 10:15','YYYY-MM-DD HH24:MI'), 'Medium', 'Pending', 0.0, NULL, NULL, NULL);
INSERT INTO Alert VALUES (6, 'STU004', 3, 4, 'Drowsiness', TO_DATE('2026-08-14 11:20','YYYY-MM-DD HH24:MI'), 'Medium', 'Acknowledged', 3.4, 'Proctor initiated alert check.', 'Faculty Three', TO_DATE('2026-08-14 11:25','YYYY-MM-DD HH24:MI'));
INSERT INTO Alert VALUES (7, 'STU005', 4, 1, 'Negligence', TO_DATE('2026-08-15 14:10','YYYY-MM-DD HH24:MI'), 'Low', 'Resolved', 0.0, 'Student requested a review.', 'Faculty One', TO_DATE('2026-08-15 14:30','YYYY-MM-DD HH24:MI'));
INSERT INTO Alert VALUES (8, 'STU001', 5, 5, 'Drowsiness', TO_DATE('2026-08-16 15:40','YYYY-MM-DD HH24:MI'), 'High', 'Pending', 6.2, NULL, NULL, NULL);

PROMPT Seeding Alert Notifications...
INSERT INTO Alert_Notifications VALUES (1, 1, 'student1@example.com', 'Email', TO_DATE('2026-08-10 09:16','YYYY-MM-DD HH24:MI'), 'Simulated', 'Alert #1: High Drowsiness sample detected in DBMS Lab (PRP353).');
INSERT INTO Alert_Notifications VALUES (2, 4, 'student1@example.com', 'Email', TO_DATE('2026-08-12 10:11','YYYY-MM-DD HH24:MI'), 'Simulated', 'Alert #4: High Drowsiness sample detected in Data Structures (PRP353).');
INSERT INTO Alert_Notifications VALUES (3, 4, '000-000-0001', 'SMS', TO_DATE('2026-08-12 10:12','YYYY-MM-DD HH24:MI'), 'Simulated', 'Sample notification for a repeated demo event.');

COMMIT;

-- ----------------------------------------------------------------------------
-- 9. VERIFICATION QUERIES (Check row counts & integrity)
-- ----------------------------------------------------------------------------
PROMPT Running schema verification check...

SELECT 'Users' AS entity, COUNT(*) AS total_rows FROM Users
UNION ALL
SELECT 'Student', COUNT(*) FROM Student
UNION ALL
SELECT 'Emergency_Contact', COUNT(*) FROM Emergency_Contact
UNION ALL
SELECT 'Proctor', COUNT(*) FROM Proctor
UNION ALL
SELECT 'Sessions', COUNT(*) FROM Sessions
UNION ALL
SELECT 'Device', COUNT(*) FROM Device
UNION ALL
SELECT 'Camera_Nodes', COUNT(*) FROM Camera_Nodes
UNION ALL
SELECT 'Alert', COUNT(*) FROM Alert
UNION ALL
SELECT 'Alert_Notifications', COUNT(*) FROM Alert_Notifications
UNION ALL
SELECT 'Audit_Log', COUNT(*) FROM Audit_Log;

PROMPT Student Drowsiness Alert System Oracle schema setup completed successfully!
