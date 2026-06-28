def fibonacci(n):
    """
    Fibonacci sayı dizisinin ilk n terimini döndürür.
    
    Args:
        n (int): Kaç terim istendiği (n >= 0)
    
    Returns:
        list: Fibonacci dizisinin ilk n terimi
    """
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib


if __name__ == "__main__":
    # Test
    print("Fibonacci ilk 10 terim:", fibonacci(10))
    print("Fibonacci ilk 1 terim:", fibonacci(1))
    print("Fibonacci ilk 0 terim:", fibonacci(0))
    print("Fibonacci ilk 5 terim:", fibonacci(5))
