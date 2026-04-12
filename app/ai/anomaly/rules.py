import pandas as pd


def rule_based_anomalies(df: pd.DataFrame, device: dict) -> list[dict]:
    """
    Fast rule-based anomaly checks. Returns list of anomaly dicts.
    device: dict with keys: device_type, rated_capacity, etc.
    """
    anomalies = []
    if df.empty:
        return anomalies

    latest = df.iloc[-1]
    power_kw = latest["power_kw"]
    rolling_mean = latest.get("rolling_mean_1h", power_kw)
    rolling_std = latest.get("rolling_std_1h", 0)
    hour = latest.get("hour_of_day", 12)
    rated = device.get("rated_capacity") or 10.0
    device_type = device.get("device_type", "")

    # 1. Overconsumption spike (>120% rated capacity)
    if abs(power_kw) > rated * 1.2:
        anomalies.append({
            "anomaly_type": "spike",
            "rule": "overconsumption",
            "expected_value": rated,
            "actual_value": power_kw,
            "z_score": None,
        })

    # 2. Solar dropout during daylight hours
    if device_type == "solar_panel" and power_kw < 0.01 and 8 <= hour <= 18:
        anomalies.append({
            "anomaly_type": "dropout",
            "rule": "solar_dropout_daylight",
            "expected_value": rated * 0.3,
            "actual_value": power_kw,
            "z_score": None,
        })

    # 3. Statistical anomaly (>3 sigma from rolling mean)
    if rolling_std > 0:
        z = abs(power_kw - rolling_mean) / rolling_std
        if z > 3.0:
            anomalies.append({
                "anomaly_type": "spike" if power_kw > rolling_mean else "dropout",
                "rule": "statistical_3sigma",
                "expected_value": rolling_mean,
                "actual_value": power_kw,
                "z_score": round(z, 2),
            })

    # 4. Battery critical SoC
    soc = latest.get("state_of_charge")
    if soc is not None and soc < 10.0:
        anomalies.append({
            "anomaly_type": "drift",
            "rule": "battery_critical",
            "expected_value": 20.0,
            "actual_value": soc,
            "z_score": None,
        })

    return anomalies
