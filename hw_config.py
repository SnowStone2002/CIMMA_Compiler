class Config:
    def __init__(self, bus_width= 256, is_depth= 1024, al= 128, pc= 16, scr= 16, os_depth= 2048, freq = 250): #default = golden case
        self.AL = al  # acc_len for all CIMs
        self.PC = pc  # parallel_channel for all CIMs
        self.SCR = scr
        self.IS_DEPTH = is_depth
        self.OS_DEPTH = os_depth
        self.BUS_WIDTH = bus_width

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
        self.freq = freq

class hwc:
    def __init__(self, config):
        self.AL = config.AL
        self.PC = config.PC
        self.SCR = config.SCR
        self.BusWidth = config.BUS_WIDTH
        self.freq = config.freq
        self.CIMsWriteWidth = config.CIMsWriteWidth
        self.CIMsComputeWidth = config.CIMsComputeWidth
        self.CIMsrows = config.CIMs_ROW
        self.MACRO_ROW = config.MACRO_ROW
        self.MACRO_COL = config.MACRO_COL
        self.CIMsParaChannel = config.PC
        self.LocalSwitchrows = config.SCR
        self.InputSRAMWidth = config.CIMsComputeWidth
        self.InputSRAMDepth = config.IS_DEPTH
        self.OutputSRAMWidth = config.PC * config.DATA_WIDTH * 4
        self.OutputSRAMDepth = config.OS_DEPTH
        self.IS_size = self.InputSRAMWidth * self.InputSRAMDepth / config.DATA_WIDTH /1024 # kB
        self.OS_size = self.OutputSRAMWidth * self.OutputSRAMDepth / config.DATA_WIDTH /1024# kB
        self.CIM_size = config.CIMs_ROW * config.CIMs_COL / config.DATA_WIDTH /1024 #kB

    
    def check(self):
        print("AXI Width:", self.BusWidth)
        print("IS Size  :", self.IS_size)
        print("OS Size  :", self.OS_size)
        print("CIM Size :", self.CIM_size)
        
