"""Public reminder links shared by date/mileage notification producers."""
def reminder_path(reminder_id):
    return f'/reminders/{int(reminder_id)}'
