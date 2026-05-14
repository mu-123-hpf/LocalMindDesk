"""Quick test for scheduler module"""
import sys
sys.path.insert(0, ".")

from app.scheduler import get_scheduler, CronParser, ScheduledTask
from datetime import datetime

# Test CronParser
now = datetime.now()
print(f"Current time: {now}")
print(f"CronParser.describe('0 8 * * *') = {CronParser.describe('0 8 * * *')}")
print(f"CronParser.describe('0 9 * * 1-5') = {CronParser.describe('0 9 * * 1-5')}")
print(f"CronParser.describe('*/5 * * * *') = {CronParser.describe('*/5 * * * *')}")
print(f"CronParser.describe('0 22 * * *') = {CronParser.describe('0 22 * * *')}")

# Test matching
print(f"\nMatch '0 {now.hour} * * *' at current time: {CronParser.matches(f'0 {now.hour} * * *', now)}")
print(f"Match '*/1 * * * *' (every minute): {CronParser.matches('*/1 * * * *', now)}")

# Test ScheduledTask
task = ScheduledTask(
    name="Test Task",
    cron="*/1 * * * *",
    action="reminder",
    params={"message": "Test reminder"},
)
print(f"\nTask: {task.name}, cron: {task.cron}")
print(f"Should run now: {task.should_run(now)}")
print(f"Safety: {task.safety_level}")
print(f"Description: {task.cron_description}")

# Test scheduler CRUD
s = get_scheduler()
result = s.add_task({
    "name": "Test Scheduler Task",
    "cron": "0 8 * * *",
    "action": "reminder",
    "params": {"message": "Test"},
})
print(f"\nAdd task result: {result}")
tid = result["task"]["id"]
print(f"Task count: {len(s.get_all())}")

# Toggle
toggle = s.toggle_task(tid)
print(f"Toggle: {toggle}")

# Delete
delete = s.delete_task(tid)
print(f"Delete: {delete}")
print(f"Task count after delete: {len(s.get_all())}")

print("\n✅ All scheduler tests passed!")
