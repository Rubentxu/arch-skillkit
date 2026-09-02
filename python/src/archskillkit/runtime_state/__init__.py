"""Runtime state that must NEVER live in the ArchitectureWorld
(ADR-0033, M0 gate): run summaries (RunLedger) and live process
tracking (RuntimeRegistry). The world event log stays knowledge-only.
"""
