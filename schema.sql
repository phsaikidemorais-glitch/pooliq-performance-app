CREATE DATABASE IF NOT EXISTS pooliq;
USE pooliq;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS swim_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    session_date DATE NOT NULL,
    goal VARCHAR(100),
    energy_level VARCHAR(30),
    pain_area VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS swim_sets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    stroke VARCHAR(50) NOT NULL,
    distance_m INT NOT NULL,
    reps INT NOT NULL,
    avg_time_seconds FLOAT NOT NULL,
    rest_seconds INT NOT NULL,
    effort_rpe INT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES swim_sessions(id) ON DELETE CASCADE
);