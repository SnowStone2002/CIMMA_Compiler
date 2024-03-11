class Config:
    def __init__(self, al, pc, scr, bus_width, is_depth, os_depth):
        self.AL = al  # acc_len for all CIMs
        self.PC = pc  # parallel_channel for all CIMs
        self.SCR = scr
        self.BUS_WIDTH = bus_width
        self.IS_DEPTH = is_depth
        self.OS_DEPTH = os_depth

        # 固定值
        self.DATA_WIDTH = 8
        self.RESULT_WIDTH = 32

        self.WEIGHT_ROW = 4
        self.WEIGHT_COL = 2

        self.SIN_AL = 64
        self.SIN_PC = 8

        # 计算衍生数据
        self.MACRO_ROW = int(self.PC / self.SIN_PC)
        self.MACRO_COL = int(self.AL / self.SIN_AL)

        self.CIM_ROW = self.SIN_PC * self.SCR * self.WEIGHT_ROW
        self.CIM_COL = self.SIN_AL * self.WEIGHT_COL

        self.CIMs_ROW = self.CIM_ROW * self.MACRO_ROW
        self.CIMs_COL = self.CIM_COL * self.MACRO_COL

        self.CIMsComputeWidth = self.SIN_AL * self.MACRO_COL * self.DATA_WIDTH
        self.CIMsWriteWidth = self.CIMs_COL

class hwc:
    def __init__(self, config):
        self.BusWidth = config.BUS_WIDTH
        self.CIMsWriteWidth = config.CIMsWriteWidth
        self.CIMsComputeWidth = config.CIMsComputeWidth
        self.CIMsrows = config.CIMs_ROW
        self.CIMsParaChannel = config.PC
        self.LocalSwitchrows = config.SCR
        self.InputSRAMWidth = config.CIMsComputeWidth
        self.InputSRAMDepth = config.IS_DEPTH
        self.OutputSRAMWidth = config.PC * config.DATA_WIDTH * 4
        self.OutputSRAMDepth = config.OS_DEPTH
