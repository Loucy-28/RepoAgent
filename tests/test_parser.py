import pytest
from app.code.parser import PythonParser, JavaParser, CodeParser
from app.db.enums import CodeLanguage


class TestPythonParser:
    def test_parse_function(self):
        code = '''
def hello(name):
    return f"Hello, {name}!"

def add(a, b):
    return a + b
'''
        parser = PythonParser()
        result = parser.parse("test.py", code)
        assert result.language == CodeLanguage.PYTHON
        assert len(result.symbols) == 2
        assert result.symbols[0].name == "hello"
        assert result.symbols[0].kind == "function"
        assert result.symbols[1].name == "add"

    def test_parse_class(self):
        code = '''
class OrderService:
    def __init__(self):
        self.orders = {}

    def create_order(self, user_id, items):
        pass
'''
        parser = PythonParser()
        result = parser.parse("test.py", code)
        assert len(result.symbols) >= 1
        class_symbols = [s for s in result.symbols if s.kind == "class"]
        assert len(class_symbols) == 1
        assert class_symbols[0].name == "OrderService"

    def test_parse_imports(self):
        code = '''
import os
import sys
from pathlib import Path
from typing import Optional, List
'''
        parser = PythonParser()
        result = parser.parse("test.py", code)
        assert "os" in result.imports
        assert "sys" in result.imports
        assert "pathlib" in result.imports
        assert "typing" in result.imports

    def test_parse_syntax_error(self):
        code = "def broken(\n"
        parser = PythonParser()
        result = parser.parse("test.py", code)
        assert result.symbols == []

    def test_parse_empty_file(self):
        parser = PythonParser()
        result = parser.parse("test.py", "")
        assert result.symbols == []
        assert result.total_lines == 0


class TestJavaParser:
    def test_parse_class(self):
        code = '''
public class OrderService {
    private Map<Integer, Order> orders = new HashMap<>();

    public Order createOrder(int userId, List<Item> items) {
        return new Order();
    }

    public Order getOrder(int orderId) {
        return orders.get(orderId);
    }
}
'''
        parser = JavaParser()
        result = parser.parse("OrderService.java", code)
        assert result.language == CodeLanguage.JAVA
        class_symbols = [s for s in result.symbols if s.kind == "class"]
        assert len(class_symbols) == 1
        assert class_symbols[0].name == "OrderService"

    def test_parse_imports(self):
        code = '''
import java.util.List;
import java.util.Map;
import com.example.Order;
'''
        parser = JavaParser()
        result = parser.parse("Test.java", code)
        assert "java.util.List" in result.imports
        assert "java.util.Map" in result.imports
        assert "com.example.Order" in result.imports


class TestCodeParser:
    def test_detect_python(self):
        parser = CodeParser()
        assert parser._detect_language("test.py") == CodeLanguage.PYTHON

    def test_detect_java(self):
        parser = CodeParser()
        assert parser._detect_language("Test.java") == CodeLanguage.JAVA

    def test_detect_unknown(self):
        parser = CodeParser()
        assert parser._detect_language("test.rb") == CodeLanguage.UNKNOWN
