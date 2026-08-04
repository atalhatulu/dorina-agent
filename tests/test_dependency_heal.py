"""Tests for dependency_heal module."""

import pytest
import subprocess
from tools.dependency_heal import missing_module, pip_name, install

def test_missing_module():
    """Test extraction of missing module name."""
    # From standard ImportError/ModuleNotFoundError message
    err = ModuleNotFoundError("No module named 'yaml'")
    assert missing_module(err) == "yaml"
    
    # From exception with 'name' attribute
    err_with_name = ImportError("Some weird message", name="cv2")
    assert missing_module(err_with_name) == "cv2"
    
    # Unknown/unparseable format
    assert missing_module(ImportError("Cannot import something")) is None
    
    # Not an ImportError
    assert missing_module(ValueError("No module named 'yaml'")) is None

def test_pip_name():
    """Test pip name mapping."""
    assert pip_name("cv2") == "opencv-python"
    assert pip_name("yaml") == "PyYAML"
    assert pip_name("PIL") == "Pillow"
    assert pip_name("bs4") == "beautifulsoup4"
    assert pip_name("unknown_module") == "unknown_module"

def test_install(monkeypatch):
    """Test install function using mock."""
    class MockProcess:
        def __init__(self, returncode):
            self.returncode = returncode
            
    def mock_run_success(*args, **kwargs):
        return MockProcess(0)
        
    def mock_run_fail(*args, **kwargs):
        return MockProcess(1)

    monkeypatch.setattr(subprocess, "run", mock_run_success)
    assert install("PyYAML") is True
    
    monkeypatch.setattr(subprocess, "run", mock_run_fail)
    assert install("invalid_package_name") is False
