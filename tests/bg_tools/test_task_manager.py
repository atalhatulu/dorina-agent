import pytest
import asyncio
from bg_tools.task_manager import TaskManager

@pytest.fixture
def manager():
    return TaskManager()

@pytest.mark.asyncio
async def test_task_start_and_complete(manager):
    """Test 1: Görev başarıyla başlar ve tamamlanır."""
    async def dummy_coro():
        return "Success"
        
    task_id = manager.start(dummy_coro(), name="Test Task 1")
    assert task_id is not None
    
    task = manager.get(task_id)
    assert task.status == "running"
    
    # Wait for the task to finish
    await asyncio.sleep(0.1)
    
    assert task.status == "done"
    assert task.result == "Success"
    
    notifs = manager.pop_notifications()
    assert len(notifs) == 1
    assert "tamamlandı" in notifs[0]
    assert "Success" in notifs[0]

@pytest.mark.asyncio
async def test_task_failure(manager):
    """Test 2: Görev hata fırlattığında doğru şekilde yakalanır ve raporlanır."""
    async def failing_coro():
        raise ValueError("Oops, something went wrong")
        
    task_id = manager.start(failing_coro(), name="Test Task 2")
    
    # Wait for the task to finish (fail)
    await asyncio.sleep(0.1)
    
    task = manager.get(task_id)
    assert task.status == "failed"
    assert "Oops" in task.error
    
    notifs = manager.pop_notifications()
    assert len(notifs) == 1
    assert "başarısız" in notifs[0]

@pytest.mark.asyncio
async def test_task_cancellation(manager):
    """Test 3: Çalışan bir görev iptal edilebilir."""
    async def long_coro():
        await asyncio.sleep(5)
        return "Done"
        
    task_id = manager.start(long_coro(), name="Test Task 3")
    
    task = manager.get(task_id)
    assert task.status == "running"
    
    # Cancel the task
    assert manager.cancel(task_id) is True
    
    # Wait for cancellation to propagate
    await asyncio.sleep(0.1)
    
    assert task.status == "cancelled"
    
    notifs = manager.pop_notifications()
    assert len(notifs) == 1
    assert "iptal edildi" in notifs[0]
    
    # Check that cancel on non-running returns False
    assert manager.cancel("invalid_id") is False
