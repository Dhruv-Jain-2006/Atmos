"""Data access. The only layer that writes SQL.

Services compose these; routers never query directly. Keeping queries here is
what makes "no N+1" an auditable property rather than a hope.
"""
