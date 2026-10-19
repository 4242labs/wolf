"""Wolf: fleet cleanup, healing, and health-check agent.

One agent, installed per machine, that trims caches, reaps stale processes,
prunes unused Docker images, checks service health, handles reboots, and
writes a structured result consumed by the consolidated SysAdmin Daily/Weekly
Report.
"""

__version__ = "0.1.0"
