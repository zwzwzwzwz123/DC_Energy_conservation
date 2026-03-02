# 1. 使用自带 Miniconda3 的基础镜像
FROM continuumio/miniconda3

# 2. 设置工作目录
WORKDIR /app

# 3. 把当前目录下的所有文件复制到容器内
COPY . /app

# 4. 根据 yml 创建纯净 conda 环境（名字叫 aircooling）
RUN conda env create -f environment.yml

# 5. 在 aircooling 环境里，安装所有的 pip 依赖包
RUN conda run -n aircooling pip install --no-cache-dir -r requirements.txt

# 6. 启动程序 (请把 main.py 替换为你实际的启动脚本名字)
CMD ["conda", "run", "-n", "aircooling", "python", "main.py"]