def summary(complaints):
    total = len(complaints)
    resolved = sum(c['status'] == 'Resolved' for c in complaints)
    return {'total': total, 'resolved': resolved, 'open': total - resolved, 'resolution_rate': round(resolved / total * 100, 1) if total else 0}
