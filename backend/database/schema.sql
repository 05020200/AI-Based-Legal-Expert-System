-- Database schema for the AI-Based Legal Expert System (Normalized)

CREATE DATABASE IF NOT EXISTS legal_expert_system;
USE legal_expert_system;

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(100),
    email VARCHAR(254) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS legal_domains (
    domain_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS legal_issues (
    issue_id INT AUTO_INCREMENT PRIMARY KEY,
    domain_id INT,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    FOREIGN KEY (domain_id) REFERENCES legal_domains(domain_id)
);

-- Facts table
CREATE TABLE IF NOT EXISTS facts (
    fact_id INT AUTO_INCREMENT PRIMARY KEY,
    fact_key VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

-- Legal concepts table
CREATE TABLE IF NOT EXISTS legal_concepts (
    concept_id INT AUTO_INCREMENT PRIMARY KEY,
    concept_key VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS legal_acts (
    act_id INT AUTO_INCREMENT PRIMARY KEY,
    act_name VARCHAR(255) NOT NULL UNIQUE,
    year INT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS legal_provisions (
    provision_id INT AUTO_INCREMENT PRIMARY KEY,
    act_id INT,
    act_name VARCHAR(255),
    section_number VARCHAR(50),
    title VARCHAR(255),
    plain_language_description TEXT,
    applicability TEXT,
    source_url VARCHAR(512),
    verification_status ENUM('pending', 'verified', 'rejected') DEFAULT 'pending',
    last_verified_date DATE,
    FOREIGN KEY (act_id) REFERENCES legal_acts(act_id)
);

CREATE TABLE IF NOT EXISTS legal_rules (
    rule_id VARCHAR(50) PRIMARY KEY,
    rule_name VARCHAR(255) NOT NULL,
    conclusion TEXT,
    explanation TEXT,
    legal_provision_reference INT,
    FOREIGN KEY (legal_provision_reference) REFERENCES legal_provisions(provision_id)
);

CREATE TABLE IF NOT EXISTS rule_conditions (
    condition_id INT AUTO_INCREMENT PRIMARY KEY,
    rule_id VARCHAR(50),
    fact_key VARCHAR(100) NOT NULL,
    operator VARCHAR(20) NOT NULL,
    expected_value VARCHAR(255) NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES legal_rules(rule_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS legal_remedies (
    remedy_id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id INT,
    remedy_description TEXT,
    FOREIGN KEY (issue_id) REFERENCES legal_issues(issue_id)
);

CREATE TABLE IF NOT EXISTS authorities (
    authority_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    jurisdiction_level VARCHAR(100),
    monetary_limit_min DECIMAL(15, 2),
    monetary_limit_max DECIMAL(15, 2),
    address TEXT
);

CREATE TABLE IF NOT EXISTS complaint_procedures (
    procedure_id INT AUTO_INCREMENT PRIMARY KEY,
    authority_id INT,
    step_number INT,
    step_description TEXT,
    FOREIGN KEY (authority_id) REFERENCES authorities(authority_id)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id INT,
    document_name VARCHAR(255),
    is_mandatory BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (issue_id) REFERENCES legal_issues(issue_id)
);

CREATE TABLE IF NOT EXISTS templates (
    template_id INT AUTO_INCREMENT PRIMARY KEY,
    document_name VARCHAR(255),
    content TEXT,
    placeholders TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    case_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    session_token VARCHAR(100) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_facts (
    fact_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    fact_key VARCHAR(100),
    fact_value TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reasoning_steps (
    step_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    rule_id VARCHAR(50),
    conclusion_reached TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES legal_rules(rule_id)
);
