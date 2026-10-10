"""ML / statistical analytics for GitPulse.

All functions are pure (pandas/numpy in, JSON-serialisable dict out) so they are unit-testable
and reusable from the API, notebooks or Airflow. Every forecast is labelled as a prediction and
accompanied by a backtest, and insufficient history is reported explicitly instead of guessed.
"""
