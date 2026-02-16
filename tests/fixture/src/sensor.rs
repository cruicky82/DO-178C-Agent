/// sensor.rs — Test fixture for DO-178C pipeline verification.
/// Sensor reading processing with match arms and Result types.

pub struct SensorConfig {
    pub min_value: f64,
    pub max_value: f64,
    pub name: String,
}

pub enum AlertLevel {
    Normal,
    Warning,
    Critical,
}

pub fn classify_reading(value: f64, config: &SensorConfig) -> Result<AlertLevel, String> {
    if value < config.min_value {
        return Err(format!("Value {} below minimum {}", value, config.min_value));
    }
    if value > config.max_value {
        return Err(format!("Value {} above maximum {}", value, config.max_value));
    }

    let range = config.max_value - config.min_value;
    let normalized = (value - config.min_value) / range;

    match normalized {
        n if n < 0.3 => Ok(AlertLevel::Normal),
        n if n < 0.7 => Ok(AlertLevel::Warning),
        _ => Ok(AlertLevel::Critical),
    }
}

pub fn process_readings(readings: &[f64], config: &SensorConfig) -> Vec<AlertLevel> {
    let mut results = Vec::new();
    for &reading in readings {
        match classify_reading(reading, config) {
            Ok(level) => results.push(level),
            Err(e) => eprintln!("Skipping invalid reading: {}", e),
        }
    }
    results
}

impl SensorConfig {
    pub fn new(name: &str, min: f64, max: f64) -> Self {
        SensorConfig {
            min_value: min,
            max_value: max,
            name: name.to_string(),
        }
    }

    pub fn is_valid(&self) -> bool {
        self.max_value > self.min_value
    }
}
