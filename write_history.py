class WriteStatusHistory:
    def __init__(self, capacity=10):
        self.capacity = capacity
        self.history = []

    def update(self, write_status):
        # 如果历史记录已满，移除最早的记录
        if len(self.history) >= self.capacity:
            self.history.pop(0)
        # 添加新的write_status到历史记录
        self.history.append(write_status)

    def get_history(self):
        return self.history
    
    def find_last_different_status(self, read_status):
    # 倒序遍历历史记录，以找到与read_status不同的最新write_status
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i] != read_status:
                # 返回这是前面第几次的write_history（基于1的索引）
                return len(self.history) - i
        # 如果所有历史记录都与read_status相同或没有历史记录，返回None或自定义消息
        return 114514
