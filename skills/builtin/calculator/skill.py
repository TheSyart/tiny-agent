"""
Calculator Skill — reliable math evaluation via Python AST (no LLM hallucination).
"""
import ast
import math
import operator
from decimal import Decimal, getcontext

from skills.base import Skill, SkillInfo
from tools.base import tool

getcontext().prec = 28

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_FUNCS = {
    "abs": abs, "round": round,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "ceil": math.ceil, "floor": math.floor,
    "exp": math.exp, "factorial": math.factorial,
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "inf": math.inf,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value)}")
    if isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.id]
        raise ValueError(f"未知变量: {node.id}")
    if isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        func = _safe_eval(node.func)
        if not callable(func):
            raise ValueError("非法调用")
        args = [_safe_eval(a) for a in node.args]
        return func(*args)
    raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


class CalculatorSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="calculator",
            description="安全的数学表达式计算器，支持四则运算、三角函数、对数等",
            version="1.0.0",
            author="builtin",
            tags=["builtin", "math", "calculator"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [calculate, unit_convert]


@tool
async def calculate(expression: str) -> str:
    """Evaluate a mathematical expression safely (no code execution).
    Supports: +−×÷, ** (power), //, %, sqrt, log, sin/cos/tan, pi, e, factorial, etc.
    Args:
        expression: Math expression, e.g. 'sqrt(2) * pi', '2**32', 'factorial(10)'
    """
    expr = expression.strip().replace('×', '*').replace('÷', '/').replace('，', ',')
    try:
        tree = ast.parse(expr, mode='eval')
        result = _safe_eval(tree)
        # Format result
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                formatted = str(int(result))
            else:
                formatted = f"{result:.10g}"
        elif isinstance(result, complex):
            formatted = str(result)
        else:
            formatted = str(result)
        return f"{expr} = {formatted}"
    except ZeroDivisionError:
        return "错误：除数为零"
    except (ValueError, TypeError) as e:
        return f"计算错误：{e}"
    except SyntaxError:
        return f"语法错误：无法解析表达式 '{expr}'"


@tool
async def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units (length, weight, temperature, area, speed).
    Args:
        value: Numeric value to convert
        from_unit: Source unit (e.g. 'km', 'kg', 'celsius', 'mph')
        to_unit: Target unit (e.g. 'miles', 'lb', 'fahrenheit', 'kph')
    """
    # Conversion factors to SI base units
    _to_si = {
        # Length (→ meters)
        "m": 1, "km": 1000, "cm": 0.01, "mm": 0.001,
        "miles": 1609.344, "mile": 1609.344,
        "ft": 0.3048, "feet": 0.3048, "foot": 0.3048,
        "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
        "yard": 0.9144, "yards": 0.9144,
        "nm": 1852,  # nautical miles
        # Weight (→ kg)
        "kg": 1, "g": 0.001, "mg": 0.000001, "t": 1000, "ton": 1000,
        "lb": 0.453592, "lbs": 0.453592, "oz": 0.0283495,
        "jin": 0.5,  # 斤
        # Speed (→ m/s)
        "m/s": 1, "km/h": 1/3.6, "kph": 1/3.6, "mph": 0.44704,
        "knot": 0.514444, "knots": 0.514444,
        # Area (→ m²)
        "m2": 1, "km2": 1e6, "cm2": 0.0001,
        "hectare": 10000, "ha": 10000, "acre": 4046.86,
        "mu": 666.667,  # 亩
    }
    _temp_units = {"celsius", "fahrenheit", "kelvin", "c", "f", "k"}

    fu = from_unit.lower().strip()
    tu = to_unit.lower().strip()

    # Temperature (special case)
    if fu in _temp_units or tu in _temp_units:
        def to_celsius(v, u):
            if u in ("celsius", "c"):   return v
            if u in ("fahrenheit", "f"): return (v - 32) * 5/9
            if u in ("kelvin", "k"):     return v - 273.15
            raise ValueError(f"未知温度单位: {u}")
        def from_celsius(v, u):
            if u in ("celsius", "c"):   return v
            if u in ("fahrenheit", "f"): return v * 9/5 + 32
            if u in ("kelvin", "k"):     return v + 273.15
            raise ValueError(f"未知温度单位: {u}")
        try:
            result = from_celsius(to_celsius(value, fu), tu)
            return f"{value} {from_unit} = {result:.4g} {to_unit}"
        except ValueError as e:
            return f"错误: {e}"

    if fu not in _to_si:
        return f"未知单位: {from_unit}"
    if tu not in _to_si:
        return f"未知单位: {to_unit}"

    si_value = value * _to_si[fu]
    result = si_value / _to_si[tu]
    return f"{value} {from_unit} = {result:.6g} {to_unit}"
