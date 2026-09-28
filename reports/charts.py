def department_series(rows):
    return [{'label': row['name'], 'received': row['total'], 'resolved': row['resolved']} for row in rows]
