-- Astabot Database Schema for MySQL
-- File: astabot_schema.sql
-- Import this file into MySQL to create the complete database structure

-- Create database
CREATE DATABASE IF NOT EXISTS astabot_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE astabot_db;

-- Users table
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    two_factor_secret VARCHAR(32) NULL,
    api_key VARCHAR(64) UNIQUE NULL,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_api_key (api_key)
);

-- User settings
CREATE TABLE user_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_setting (user_id, setting_key),
    INDEX idx_user_id (user_id),
    INDEX idx_setting_key (setting_key)
);

-- Trading accounts (for broker integrations)
CREATE TABLE trading_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    broker_name VARCHAR(50) NOT NULL, -- 'metatrader5', 'alpaca', 'interactive_brokers'
    account_name VARCHAR(100) NOT NULL,
    account_id VARCHAR(100) UNIQUE NOT NULL,
    api_key VARCHAR(256) NULL,
    api_secret VARCHAR(256) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_paper_trading BOOLEAN DEFAULT TRUE,
    balance DECIMAL(15,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_sync TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_broker_name (broker_name),
    INDEX idx_account_id (account_id)
);

-- Assets/Markets
CREATE TABLE assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    asset_type ENUM('forex', 'crypto', 'stock', 'commodity', 'index') NOT NULL,
    base_currency VARCHAR(3) NOT NULL,
    quote_currency VARCHAR(3) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    pip_value DECIMAL(10,5) DEFAULT 0.00001,
    contract_size INT DEFAULT 100000,
    min_lot_size DECIMAL(10,5) DEFAULT 0.01,
    max_lot_size DECIMAL(10,5) DEFAULT 100.00,
    lot_step DECIMAL(10,5) DEFAULT 0.01,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_symbol (symbol),
    INDEX idx_asset_type (asset_type),
    INDEX idx_is_active (is_active)
);

-- Trading signals
CREATE TABLE signals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL, -- NULL for system-generated signals
    asset_id INT NOT NULL,
    signal_type ENUM('buy', 'sell') NOT NULL,
    entry_price DECIMAL(15,5) NOT NULL,
    stop_loss DECIMAL(15,5) NULL,
    take_profit DECIMAL(15,5) NULL,
    confidence_score DECIMAL(3,2) NULL, -- 0.00 to 1.00
    timeframe VARCHAR(10) NOT NULL, -- '5m', '15m', '1h', '4h', '1d'
    strategy_name VARCHAR(100) NULL,
    signal_strength ENUM('weak', 'medium', 'strong') DEFAULT 'medium',
    is_active BOOLEAN DEFAULT TRUE,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP NULL,
    pnl DECIMAL(15,2) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_asset_id (asset_id),
    INDEX idx_signal_type (signal_type),
    INDEX idx_timeframe (timeframe),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at)
);

-- Backtest results
CREATE TABLE backtests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    asset_id INT NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    period VARCHAR(20) NOT NULL, -- '1mo', '3mo', '6mo', '1y', '2y'
    timeframe VARCHAR(10) NOT NULL, -- '5m', '15m', '1h', '1d'
    initial_capital DECIMAL(15,2) NOT NULL,
    final_capital DECIMAL(15,2) NOT NULL,
    total_trades INT NOT NULL,
    winning_trades INT NOT NULL,
    losing_trades INT NOT NULL,
    win_rate DECIMAL(5,2) NOT NULL,
    total_pnl DECIMAL(15,2) NOT NULL,
    max_drawdown DECIMAL(15,2) NOT NULL,
    profit_factor DECIMAL(10,2) NULL,
    sharpe_ratio DECIMAL(10,2) NULL,
    avg_win DECIMAL(15,2) NULL,
    avg_loss DECIMAL(15,2) NULL,
    max_consecutive_wins INT DEFAULT 0,
    max_consecutive_losses INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_asset_id (asset_id),
    INDEX idx_created_at (created_at)
);

-- Live trades/orders
CREATE TABLE trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    trading_account_id INT NOT NULL,
    asset_id INT NOT NULL,
    order_type ENUM('market', 'limit', 'stop', 'stop_limit') NOT NULL,
    side ENUM('buy', 'sell') NOT NULL,
    quantity DECIMAL(15,5) NOT NULL,
    price DECIMAL(15,5) NULL, -- NULL for market orders
    stop_price DECIMAL(15,5) NULL,
    limit_price DECIMAL(15,5) NULL,
    status ENUM('pending', 'filled', 'cancelled', 'rejected', 'partial') DEFAULT 'pending',
    filled_quantity DECIMAL(15,5) DEFAULT 0,
    remaining_quantity DECIMAL(15,5) NULL,
    commission DECIMAL(10,2) DEFAULT 0,
    broker_order_id VARCHAR(100) NULL,
    signal_id INT NULL,
    strategy_name VARCHAR(100) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    filled_at TIMESTAMP NULL,
    cancelled_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (trading_account_id) REFERENCES trading_accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_trading_account_id (trading_account_id),
    INDEX idx_asset_id (asset_id),
    INDEX idx_status (status),
    INDEX idx_side (side),
    INDEX idx_created_at (created_at)
);

-- Portfolio positions
CREATE TABLE positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    trading_account_id INT NOT NULL,
    asset_id INT NOT NULL,
    side ENUM('long', 'short') NOT NULL,
    quantity DECIMAL(15,5) NOT NULL,
    avg_entry_price DECIMAL(15,5) NOT NULL,
    current_price DECIMAL(15,5) NULL,
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    stop_loss DECIMAL(15,5) NULL,
    take_profit DECIMAL(15,5) NULL,
    is_open BOOLEAN DEFAULT TRUE,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP NULL,
    closed_price DECIMAL(15,5) NULL,
    realized_pnl DECIMAL(15,2) NULL,
    commission DECIMAL(10,2) DEFAULT 0,
    notes TEXT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (trading_account_id) REFERENCES trading_accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_trading_account_id (trading_account_id),
    INDEX idx_asset_id (asset_id),
    INDEX idx_is_open (is_open),
    INDEX idx_side (side)
);

-- Market data cache
CREATE TABLE market_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open_price DECIMAL(15,5) NOT NULL,
    high_price DECIMAL(15,5) NOT NULL,
    low_price DECIMAL(15,5) NOT NULL,
    close_price DECIMAL(15,5) NOT NULL,
    volume BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    UNIQUE KEY unique_asset_timeframe_timestamp (asset_id, timeframe, timestamp),
    INDEX idx_asset_id (asset_id),
    INDEX idx_timeframe (timeframe),
    INDEX idx_timestamp (timestamp)
);

-- API usage logs
CREATE TABLE api_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INT NOT NULL,
    response_time DECIMAL(10,3) NULL, -- in seconds
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_endpoint (endpoint),
    INDEX idx_created_at (created_at),
    INDEX idx_status_code (status_code)
);

-- System logs
CREATE TABLE system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') NOT NULL,
    module VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    traceback TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_level (level),
    INDEX idx_module (module),
    INDEX idx_created_at (created_at)
);

-- Notifications
CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type ENUM('info', 'success', 'warning', 'error') DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_is_read (is_read),
    INDEX idx_created_at (created_at)
);

-- ML Model Performance
CREATE TABLE ml_models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50) NOT NULL, -- 'random_forest', 'xgboost', 'neural_network'
    asset_id INT NULL,
    accuracy_score DECIMAL(5,4) NULL,
    precision_score DECIMAL(5,4) NULL,
    recall_score DECIMAL(5,4) NULL,
    f1_score DECIMAL(5,4) NULL,
    training_data_points INT NULL,
    test_data_points INT NULL,
    model_file_path VARCHAR(255) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_asset_id (asset_id),
    INDEX idx_model_type (model_type),
    INDEX idx_is_active (is_active)
);

-- Insert default assets
INSERT INTO assets (symbol, name, asset_type, base_currency, quote_currency, pip_value, contract_size) VALUES
('XAU/USD', 'Gold vs US Dollar', 'commodity', 'XAU', 'USD', 0.01, 100),
('EUR/USD', 'Euro vs US Dollar', 'forex', 'EUR', 'USD', 0.00001, 100000),
('BTC/USD', 'Bitcoin vs US Dollar', 'crypto', 'BTC', 'USD', 0.01, 1),
('ETH/USD', 'Ethereum vs US Dollar', 'crypto', 'ETH', 'USD', 0.01, 1),
('GBP/USD', 'British Pound vs US Dollar', 'forex', 'GBP', 'USD', 0.00001, 100000),
('USD/JPY', 'US Dollar vs Japanese Yen', 'forex', 'USD', 'JPY', 0.001, 100000),
('SPY', 'SPDR S&P 500 ETF', 'stock', 'SPY', 'USD', 0.01, 1),
('AAPL', 'Apple Inc.', 'stock', 'AAPL', 'USD', 0.01, 1);

-- Insert default admin user (password: admin123 - CHANGE THIS!)
INSERT INTO users (username, email, password_hash, is_admin, email_verified) VALUES
('admin', 'admin@astabot.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LeCt1uB5Y2YH3L9q', TRUE, TRUE);

-- Insert default user settings
INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES
(1, 'theme', 'dark'),
(1, 'timezone', 'America/New_York'),
(1, 'default_capital', '10000'),
(1, 'risk_per_trade', '1'),
(1, 'max_daily_loss', '5'),
(1, 'email_notifications', 'true'),
(1, 'signal_alerts', 'true'),
(1, 'market_hours_alerts', 'true');

-- Create indexes for performance
CREATE INDEX idx_signals_user_asset ON signals(user_id, asset_id);
CREATE INDEX idx_trades_user_date ON trades(user_id, created_at);
CREATE INDEX idx_positions_user_open ON positions(user_id, is_open);
CREATE INDEX idx_market_data_asset_time ON market_data(asset_id, timeframe, timestamp DESC);

-- Create views for common queries
CREATE VIEW user_portfolio_summary AS
SELECT
    u.username,
    ta.account_name,
    a.symbol,
    p.side,
    p.quantity,
    p.avg_entry_price,
    p.current_price,
    p.unrealized_pnl,
    p.opened_at
FROM positions p
JOIN users u ON p.user_id = u.id
JOIN trading_accounts ta ON p.trading_account_id = ta.id
JOIN assets a ON p.asset_id = a.id
WHERE p.is_open = TRUE;

-- Vista comentada por compatibilidad - requiere columna pnl en trades
-- CREATE VIEW signal_performance AS
-- SELECT
--     s.asset_id,
--     a.symbol,
--     s.signal_type,
--     COUNT(*) as total_signals,
--     AVG(s.confidence_score) as avg_confidence,
--     SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
--     AVG(CASE WHEN t.pnl IS NOT NULL THEN t.pnl ELSE 0 END) as avg_pnl
-- FROM signals s
-- LEFT JOIN assets a ON s.asset_id = a.id
-- LEFT JOIN trades t ON s.id = t.signal_id
-- GROUP BY s.asset_id, a.symbol, s.signal_type;

-- Triggers for automatic updates
DELIMITER //

CREATE TRIGGER update_position_pnl
    BEFORE UPDATE ON positions
    FOR EACH ROW
BEGIN
    IF NEW.current_price IS NOT NULL AND OLD.avg_entry_price IS NOT NULL THEN
        IF NEW.side = 'long' THEN
            SET NEW.unrealized_pnl = (NEW.current_price - OLD.avg_entry_price) * NEW.quantity;
        ELSE
            SET NEW.unrealized_pnl = (OLD.avg_entry_price - NEW.current_price) * NEW.quantity;
        END IF;
    END IF;
END//

CREATE TRIGGER log_system_events
    AFTER INSERT ON system_logs
    FOR EACH ROW
BEGIN
    -- Could add additional logging logic here
    IF NEW.level = 'ERROR' OR NEW.level = 'CRITICAL' THEN
        -- Send alert to admin (placeholder for notification system)
        INSERT INTO notifications (user_id, title, message, type)
        SELECT id, 'System Alert', CONCAT('System error: ', LEFT(NEW.message, 200)), 'error'
        FROM users WHERE is_admin = TRUE;
    END IF;
END//

DELIMITER ;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON astabot_db.* TO 'astabot_user'@'localhost' IDENTIFIED BY 'secure_password_here';
-- FLUSH PRIVILEGES;