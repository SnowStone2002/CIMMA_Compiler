import subprocess

def run_compiler_count(params):
    # 构建命令行命令
    cmd = ['./compiler_count'] + [str(param) for param in params]
    
    # 使用subprocess调用命令
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 返回输出结果
    return result.stdout, result.stderr

# 设计变量的范例扫描范围
bus_width_options = [512]
al_options = [64, 128]
pc_options = [64]
scr_options = [1]
is_depth_options = [32]
os_depth_options = [16]
freq_options = [500]
operation_options = ["mvm"]
weight_map_channel_options = [100, 200]
weight_map_length_options = [400, 600]
input_map_length_options = [300]
input_map_channel_options = ["wspp"]  # 注意这里是data_stream参数，与前面的参数顺序有所不同

# 参数化扫描
for bus_width in bus_width_options:
    for al in al_options:
        for pc in pc_options:
            for scr in scr_options:
                for is_depth in is_depth_options:
                    for os_depth in os_depth_options:
                        for freq in freq_options:
                            for operation in operation_options:
                                for weight_map_channel in weight_map_channel_options:
                                    for weight_map_length in weight_map_length_options:
                                        for input_map_length in input_map_length_options:
                                            for data_stream in input_map_channel_options:
                                                # 组装参数
                                                params = [
                                                    bus_width, al, pc, scr, is_depth, os_depth, freq, 
                                                    operation, weight_map_channel, weight_map_length, 
                                                    input_map_length, data_stream
                                                ]
                                                stdout, stderr = run_compiler_count(params)
                                                if stdout:
                                                    print("Output:\n", stdout)
                                                if stderr:
                                                    print("Error:\n", stderr)
