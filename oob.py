import torch

class TensorStack:
    def __init__(self, element_width):
        self.stack = []  # 使用列表来存储栈中的元素
        self.element_width = element_width  # 每个元素的宽度

    def push(self, new_element):
        self.stack.append(new_element)

    def pop(self):
        if self.is_empty():
            return None  # 如果栈为空，则返回None
        return self.stack.pop()
    
    def is_empty(self):
        return len(self.stack) == 0

    def size(self):
        return len(self.stack)