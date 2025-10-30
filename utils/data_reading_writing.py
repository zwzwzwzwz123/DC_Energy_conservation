import pandas as pd
from influxdb import DataFrameClient
import datetime
import json
import pytz


# ==================== 新增：适配新YAML格式的辅助函数 ====================

def _extract_uids_from_air_conditioners(uid_config, measurement_point_names=None):
    """
    从新格式的 uid_config 中提取 UID 列表
    
    Args:
        uid_config: 配置字典
        measurement_point_names: 要提取的测点名称列表，None表示提取所有
        
    Returns:
        list: UID列表
    """
    uids = []
    air_conditioners = uid_config.get('air_conditioners', {})
    
    for ac_name, ac_info in air_conditioners.items():
        measurement_points = ac_info.get('measurement_points', {})
        
        if measurement_point_names is None:
            # 提取所有测点的UID
            uids.extend(measurement_points.values())
        else:
            # 只提取指定测点名称的UID
            for point_name in measurement_point_names:
                if point_name in measurement_points:
                    uids.append(measurement_points[point_name])
    
    return uids


def _get_air_conditioner_uids_and_names(uid_config):
    """
    从新格式的 uid_config 中提取空调UID和名称列表
    
    Args:
        uid_config: 配置字典
        
    Returns:
        tuple: (uids列表, names列表)
    """
    air_conditioners = uid_config.get('air_conditioners', {})
    
    uids = []
    names = []
    
    for ac_name, ac_info in air_conditioners.items():
        # 尝试从测点中获取开关机相关的UID作为设备UID
        measurement_points = ac_info.get('measurement_points', {})
        
        # 优先查找开关机相关的UID
        device_uid = None
        for key in ['监控开关机', '监控开关机状态', '开关机命令']:
            if key in measurement_points:
                device_uid = measurement_points[key]
                break
        
        # 如果没有找到开关机UID，使用温度设定点作为代表
        if device_uid is None:
            for key in ['温度设定值', '温度设定点', '回风温度设定点（℃）', '送风温度设置点']:
                if key in measurement_points:
                    device_uid = measurement_points[key]
                    break
        
        if device_uid:
            uids.append(device_uid)
            names.append(ac_info.get('device_name', ac_name))
    
    return uids, names


def _map_measurement_points_to_uids(uid_config, ac_name, point_names):
    """
    将空调的测点名称映射到UID
    
    Args:
        uid_config: 配置字典
        ac_name: 空调名称
        point_names: 测点名称列表
        
    Returns:
        dict: {测点名称: UID}
    """
    air_conditioners = uid_config.get('air_conditioners', {})
    
    if ac_name not in air_conditioners:
        return {}
    
    measurement_points = air_conditioners[ac_name].get('measurement_points', {})
    
    result = {}
    for point_name in point_names:
        if point_name in measurement_points:
            result[point_name] = measurement_points[point_name]
    
    return result

# ==================== 原有函数（已修改以兼容新格式）====================


def get_measurements_tags_fields(uid_config, uid_type, measurements_fields_dict):
    """
    通过 uid_config.yaml 生成 uid 与数据值的映射关系
    InfluxDB 1.x新结构：直接使用uid作为measurement，不使用tags
    
    支持两种格式：
    1. 旧格式：uid_config[uid_type] = {measurement_uid: [uid1, uid2]}
    2. 新格式：uid_config['air_conditioners'] = {ac_name: {measurement_points: {point_name: uid}}}
    """
    uid_values_mapping = {}
    
    # 尝试旧格式
    data_uid = uid_config.get(uid_type)
    
    if data_uid is not None:
        # 旧格式逻辑
        # 生成映射字典：键：clean_measurement，值：measurement（如 "indoor_temperature_sensor" ："indoor_temperature_sensor_uid"）
        clean_to_original_mapping = {measurement.replace('_uid', ''): measurement for measurement in data_uid.keys()}

        # 遍历传入的字典
        for clean_measurement, values in measurements_fields_dict.items():
            # 验证measurement是否存在
            original_measurement = clean_to_original_mapping.get(clean_measurement)
            if original_measurement is None:
                raise ValueError(f"未找到measurement配置: '{clean_measurement}'")

            # 获取该measurement对应的uid列表
            uids = data_uid[original_measurement]
            # 验证字段数量是否匹配
            if len(values) != len(uids):
                raise ValueError(
                    f"字段数量不匹配: measurement '{clean_measurement}' 应有 {len(uids)} 个值，但传入了 {len(values)} 个值"
                )

            # 直接将uid和值进行映射（新结构：uid作为measurement）
            for uid, value in zip(uids, values):
                uid_values_mapping[uid] = value
    else:
        # 新格式逻辑：从 air_conditioners 中提取
        # measurements_fields_dict 格式: {ac_name: {point_name: value}}
        air_conditioners = uid_config.get('air_conditioners', {})
        
        for ac_name, point_values in measurements_fields_dict.items():
            if ac_name not in air_conditioners:
                raise ValueError(f"未找到空调配置: '{ac_name}'")
            
            measurement_points = air_conditioners[ac_name].get('measurement_points', {})
            
            for point_name, value in point_values.items():
                if point_name not in measurement_points:
                    raise ValueError(f"空调 '{ac_name}' 中未找到测点: '{point_name}'")
                
                uid = measurement_points[point_name]
                uid_values_mapping[uid] = value

    def get_value_by_uid(uid):
        return uid_values_mapping.get(uid)  # 根据uid查询数据值

    return uid_values_mapping, get_value_by_uid
    # uid_values_mapping：uid与数据值的直接映射；get_value_by_uid：根据uid获取数据值


def generate_points(uid_values_mapping, get_value_by_uid):
    """
    生成 InfluxDB 1.x 新结构格式的数据点
    新结构：uid直接作为measurement，不使用tags，field固定为"value"
    """
    current_timestamp = datetime.datetime.now(datetime.UTC)  # 时间戳
    points = []

    # 遍历所有uid和对应的值
    for uid, value in uid_values_mapping.items():
        point = {
            "measurement": uid,  # 直接使用uid作为measurement
            "time": current_timestamp,
            "fields": {"value": value}  # field固定为"value"
            # 完全移除tags字段
        }
        points.append(point)

    return points


def writing_data_to_influxdb(client, database, points):
    # 确保客户端连接到正确的数据库
    client.switch_database(database)
    # 批量写入数据点
    client.write_points(points)


_dataframe_clients = {}  # 客户端缓存字典


def get_dataframe_client(client):
    """获取或创建DataFrameClient实例"""
    client_key = f"{client._host}:{client._port}:{client._database}"

    if client_key not in _dataframe_clients:
        _dataframe_clients[client_key] = DataFrameClient(
            host=client._host,
            port=client._port,
            username=client._username,
            password=client._password,
            database=client._database
        )

    return _dataframe_clients[client_key]


# 读取数据库函数
def reading_data_query(influxdb_config, uid_config, reading_data_client, query_range="-1h", query_measurement=None,
                       enable_unified_sampling=False, target_interval_seconds=30):
    """
    从InfluxDB 1.x读取数据并返回pandas DataFrame
    新结构：直接查询uid作为measurement的数据

    Args:
        influxdb_config: InfluxDB配置
        uid_config: UID配置
        reading_data_client: 数据库客户端
        query_range: 查询时间范围，默认"-1h"
        query_measurement: 查询的measurement列表，默认None（查询全部）
        enable_unified_sampling: 是否启用统一采样处理，默认False
        target_interval_seconds: 目标采样间隔（秒），默认30秒

    Returns:
        pd.DataFrame: 查询结果DataFrame
    """
    # 获取数据库名称
    client_name = str(reading_data_client._database)  # 获取客户端的数据库名称

    # 根据客户端确定对应的uid配置键
    if "iot_origin_database" in client_name:
        query_uid = "dc_status_data_uid"
    elif "prediction_data_db" in client_name:
        query_uid = "prediction_data_uid"
    elif "setting_data_db" in client_name:
        query_uid = "setting_data_uid"
    elif "reference_data_db" in client_name:
        query_uid = "reference_data_uid"
    else:
        # 兜底逻辑：尝试从客户端属性推断
        query_uid = "dc_status_data_uid"

    # 获取要查询的uid列表
    # 尝试旧格式
    query_measurement_uid = uid_config.get(query_uid)
    
    if query_measurement_uid is not None:
        # 旧格式逻辑
        if query_measurement is None:
            # 获取所有uid
            all_uids = []
            for measurement_key, uids in query_measurement_uid.items():
                all_uids.extend(uids)
            query_uids = all_uids
        else:
            # 根据指定的measurement类型获取对应的uid
            query_uids = []
            for measurement in query_measurement:
                measurement_key = measurement + "_uid"
                if measurement_key in query_measurement_uid:
                    query_uids.extend(query_measurement_uid[measurement_key])
    else:
        # 新格式逻辑：从 air_conditioners 中提取
        if query_measurement is None:
            # 获取所有测点的uid
            query_uids = _extract_uids_from_air_conditioners(uid_config)
        else:
            # 根据指定的测点名称获取对应的uid
            query_uids = _extract_uids_from_air_conditioners(uid_config, query_measurement)

    time_condition = _convert_time_range_to_influxql(query_range)
    dataframe_client = get_dataframe_client(reading_data_client)

    # 查询所有uid的数据（新结构：uid作为measurement）
    all_data = []
    for uid in query_uids:
        influxql_query = f'''
            SELECT "value"
            FROM "{uid}"
            WHERE {time_condition}
            '''

        try:
            result = dataframe_client.query(influxql_query)
            if uid in result and not result[uid].empty:
                df = result[uid].copy()
                df['_uid'] = uid  # 保存uid信息用于后续处理
                all_data.append(df)
        except Exception as e:
            # 如果某个measurement不存在数据，继续查询其他的
            continue

    # 合并所有数据
    if not all_data:
        # 如果没有数据，返回空DataFrame但保持正确的列结构
        return pd.DataFrame(columns=['_time'])

    # 合并所有DataFrame
    combined_df = pd.concat(all_data, ignore_index=False)

    # 转换为与原函数相同的格式（保持接口兼容性）
    query_result = _format_dataframe_like_flux_result_new_structure(combined_df, uid_config, query_uid)

    # 如果启用统一采样处理
    if enable_unified_sampling and not query_result.empty:
        # 导入数据处理模块（避免循环导入）
        from . import data_processing
        # 应用统一采样处理
        unified_result = data_processing.unify_sensor_data_sampling(query_result, uid_config, query_uid,
                                                                    target_interval_seconds)

        # 验证处理结果
        validation_result = data_processing.validate_unified_data_consistency(unified_result, uid_config, query_uid)

        if validation_result['is_valid']:
            query_result = unified_result

    return query_result


def _convert_time_range_to_influxql(flux_time_range):
    """
    将Flux时间范围格式转换为InfluxQL格式
    例如："-1h" -> "time > now() - 1h"
    """
    if flux_time_range.startswith("-"):
        time_value = flux_time_range[1:]  # 去掉负号
        return f"time > now() - {time_value}"
    else:
        # 如果是绝对时间，需要进一步处理
        return f"time > '{flux_time_range}'"


def _format_dataframe_like_flux_result_new_structure(df, uid_config, query_uid):
    """
    将新结构的DataFrame格式化为与原Flux查询结果相同的格式
    保持接口兼容性：将uid映射回measurement+uid的列名格式
    """
    if df.empty:
        return pd.DataFrame(columns=['_time'])

    # 重置索引，将时间索引转换为列
    df = df.reset_index()
    df = df.rename(columns={'index': '_time'})

    # 创建uid到measurement类型的映射
    uid_to_measurement = {}
    
    # 尝试旧格式
    query_measurement_uid = uid_config.get(query_uid)
    
    if query_measurement_uid is not None:
        # 旧格式逻辑
        for measurement_key, uids in query_measurement_uid.items():
            measurement_type = measurement_key.replace('_uid', '')
            for uid in uids:
                uid_to_measurement[uid] = measurement_type
    else:
        # 新格式逻辑：从 air_conditioners 中创建映射
        air_conditioners = uid_config.get('air_conditioners', {})
        for ac_name, ac_info in air_conditioners.items():
            measurement_points = ac_info.get('measurement_points', {})
            for point_name, uid in measurement_points.items():
                # 使用空调名称+测点名称作为measurement类型
                uid_to_measurement[uid] = f"{ac_name}_{point_name}"

    # 创建透视表
    pivot_df = df.pivot_table(
        index='_time',
        columns='_uid',
        values='value',
        aggfunc='first'  # 如果有重复值，取第一个
    )

    # 重命名列以保持与原格式的兼容性
    new_columns = {}
    for uid in pivot_df.columns:
        measurement_type = uid_to_measurement.get(uid, 'unknown')
        new_columns[uid] = f"{measurement_type}_{uid}"

    pivot_df = pivot_df.rename(columns=new_columns)

    # 重置索引并按时间降序排序
    result_df = pivot_df.reset_index()
    result_df = result_df.sort_values('_time', ascending=False).reset_index(drop=True)

    return result_df


def _format_dataframe_like_flux_result(df):
    """
    保留原有的格式化函数以防需要（向后兼容）
    将DataFrame格式化为与Flux查询结果相同的格式
    实现数据透视，使每个measurement+number_uid组合成为一列
    """
    if df.empty:
        return pd.DataFrame(columns=['_time'])

    # 重置索引，将时间索引转换为列
    df = df.reset_index()
    df = df.rename(columns={'index': '_time'})

    # 创建透视表，类似于Flux的pivot操作
    pivot_df = df.pivot_table(
        index='_time',
        columns=['_measurement', 'number_uid'],
        values='value',
        aggfunc='first'  # 如果有重复值，取第一个
    )

    # 展平多级列索引
    pivot_df.columns = [f"{measurement}_{uid}" for measurement, uid in pivot_df.columns]

    # 重置索引并按时间降序排序
    result_df = pivot_df.reset_index()
    result_df = result_df.sort_values('_time', ascending=False).reset_index(drop=True)

    return result_df


# prediction_data写入
def prediction_data_writing(influxdb_config, uid_config, prediction_data_measurements_fields, prediction_data_client):
    """写入预测数据到InfluxDB 1.x（新结构：uid作为measurement）"""
    database = influxdb_config["influxdb_prediction_data"]["database"]
    uid_values_mapping, get_value_by_uid = get_measurements_tags_fields(
        uid_config, "prediction_data_uid", prediction_data_measurements_fields)
    prediction_data_points = generate_points(uid_values_mapping, get_value_by_uid)
    writing_data_to_influxdb(prediction_data_client, database, prediction_data_points)


# setting_data写入
def setting_data_writing(influxdb_config, uid_config, setting_data_measurements_fields, setting_data_client):
    """写入设置数据到InfluxDB 1.x（新结构：uid作为measurement）"""
    database = influxdb_config["influxdb_setting_data"]["database"]
    uid_values_mapping, get_value_by_uid = get_measurements_tags_fields(
        uid_config, "setting_data_uid", setting_data_measurements_fields)
    setting_data_points = generate_points(uid_values_mapping, get_value_by_uid)
    writing_data_to_influxdb(setting_data_client, database, setting_data_points)


# reference_data写入
def reference_data_writing(influxdb_config, uid_config, reference_data_measurements_fields, reference_data_client):
    """写入参考数据到InfluxDB 1.x（新结构：uid作为measurement）"""
    database = influxdb_config["influxdb_reference_data"]["database"]
    uid_values_mapping, get_value_by_uid = get_measurements_tags_fields(
        uid_config, "reference_data_uid", reference_data_measurements_fields)
    reference_data_points = generate_points(uid_values_mapping, get_value_by_uid)
    writing_data_to_influxdb(reference_data_client, database, reference_data_points)


def convert_iso_to_beijing_time(iso_timestamp):
    """
    将ISO格式时间戳转换为中国大陆北京时间字符串

    Args:
        iso_timestamp: ISO格式时间戳字符串或datetime对象

    Returns:
        str: 北京时间字符串，格式：YYYY-MM-DD HH:MM:SS
    """
    try:
        if isinstance(iso_timestamp, str):
            # 解析ISO格式时间戳
            dt = datetime.datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        elif isinstance(iso_timestamp, datetime.datetime):
            dt = iso_timestamp
        else:
            # 如果是其他类型，使用当前UTC时间
            dt = datetime.datetime.now(datetime.UTC)

        # 确保时区信息
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.UTC)

        # 转换为北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        beijing_time = dt.astimezone(beijing_tz)

        # 格式化为字符串
        return beijing_time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        # 如果转换失败，返回当前北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_beijing = datetime.datetime.now(beijing_tz)
        return current_beijing.strftime('%Y-%m-%d %H:%M:%S')


def generate_optimization_result_points(uid_config, optimization_result, measurement_name, is_auto_execute):
    """
    为optimization_result数据生成InfluxDB 1.x格式的数据点
    每台空调生成一个独立的point

    Args:
        uid_config: UID配置信息
        optimization_result: 优化结果数据
        measurement_name: measurement名称（ai_energy_saving_suggestions 或 ai_energy_saving_reference）
        is_auto_execute: 是否自动执行

    Returns:
        list: InfluxDB数据点列表
    """
    points = []
    current_timestamp = datetime.datetime.now(datetime.UTC)
    beijing_time_str = convert_iso_to_beijing_time(current_timestamp)

    # 获取空调设备信息 - 兼容新旧格式
    if 'device_uid' in uid_config:
        # 旧格式
        air_conditioner_uids = uid_config['device_uid']['air_conditioner_uid']
        air_conditioner_names = uid_config['device_uid']['air_conditioner_name']
    else:
        # 新格式：从 air_conditioners 中提取
        air_conditioner_uids, air_conditioner_names = _get_air_conditioner_uids_and_names(uid_config)
    
    room_name = uid_config.get('room_name', '未知机房')

    # 获取优化结果数据
    temperatures = optimization_result.get('air_conditioner_setting_temperature', [])
    humidities = optimization_result.get('air_conditioner_setting_humidity', [])
    onoff_settings = optimization_result.get('air_conditioner_cooling_mode', [])

    # 制冷系统配置映射
    # 根据README.md和uid_config.yaml：
    # - 艾特网能空调1#和2#：每台2个制冷系统
    # - 其他空调：每台1个制冷系统
    cooling_system_config = [
        {"name": "艾特网能空调1#", "systems": 2},  # 索引0
        {"name": "艾特网能空调2#", "systems": 2},  # 索引1
        {"name": "美的空调", "systems": 1},        # 索引2
        {"name": "维谛精密空调1", "systems": 1},    # 索引3
        {"name": "维谛空调2", "systems": 1},       # 索引4
        {"name": "维谛空调3", "systems": 1}        # 索引5
    ]

    # 为每台空调生成一个point
    onoff_index = 0  # 用于跟踪onoff_settings数组的索引

    for i in range(len(air_conditioner_uids)):
        if i < len(air_conditioner_names):
            device_uid = air_conditioner_uids[i]
            device_name = air_conditioner_names[i]

            # 获取该空调的设置参数
            temperature = temperatures[i] if i < len(temperatures) else 25
            humidity = humidities[i] if i < len(humidities) else 50

            # 根据空调类型处理制冷模式
            if i < len(cooling_system_config):
                systems_count = cooling_system_config[i]["systems"]

                if systems_count == 2:  # 艾特网能空调（双系统）
                    # 获取两个系统的制冷模式
                    system1_mode = onoff_settings[onoff_index] if onoff_index < len(onoff_settings) else 1
                    system2_mode = onoff_settings[onoff_index + 1] if (onoff_index + 1) < len(onoff_settings) else 1

                    # 构建制冷模式数据（包含两个系统）
                    cooling_mode_data = {
                        "system1": system1_mode,
                        "system2": system2_mode
                    }
                    onoff_index += 2
                else:  # 其他空调（单系统）
                    # 获取单个系统的制冷模式
                    single_mode = onoff_settings[onoff_index] if onoff_index < len(onoff_settings) else 1
                    cooling_mode_data = single_mode
                    onoff_index += 1
            else:
                # 默认单系统
                cooling_mode_data = onoff_settings[onoff_index] if onoff_index < len(onoff_settings) else 1
                onoff_index += 1

            # 构建JSON数据
            json_data = {
                "room_name": room_name,
                "generate_time": beijing_time_str,
                "is_auto_execute": is_auto_execute,
                "device_name": device_name,
                "device_uid": device_uid,
                "air_conditioner_cooling_mode": cooling_mode_data,
                "air_conditioner_setting_temperature": temperature,
                "air_conditioner_setting_humidity": humidity
            }

            # 创建数据点
            point = {
                "measurement": measurement_name,
                "time": current_timestamp,
                "fields": {"value": json.dumps(json_data, ensure_ascii=False)}
            }
            points.append(point)

    return points


def optimization_result_writing_suggestions(influxdb_config, uid_config, optimization_result,
                                           setting_data_client, is_auto_execute):
    """
    将optimization_result数据写入setting_data_client作为ai_energy_saving_suggestions
    用于子线程1（实际优化）

    Args:
        influxdb_config: InfluxDB配置信息
        uid_config: UID配置信息
        optimization_result: 优化结果数据
        setting_data_client: 设置数据客户端
        is_auto_execute: 是否自动执行
    """
    try:
        database = influxdb_config["influxdb_setting_data"]["database"]

        # 生成ai_energy_saving_suggestions数据点
        suggestions_points = generate_optimization_result_points(
            uid_config, optimization_result, "ai_energy_saving_suggestions", is_auto_execute
        )

        # 写入setting_data_client
        writing_data_to_influxdb(setting_data_client, database, suggestions_points)

    except Exception as e:
        raise Exception(f"写入ai_energy_saving_suggestions数据时发生错误: {str(e)}")


def optimization_result_writing_reference(influxdb_config, uid_config, optimization_result,
                                         reference_data_client, is_auto_execute):
    """
    将optimization_result数据写入reference_data_client作为ai_energy_saving_reference
    用于子线程3（参考优化）

    Args:
        influxdb_config: InfluxDB配置信息
        uid_config: UID配置信息
        optimization_result: 优化结果数据
        reference_data_client: 参考数据客户端
        is_auto_execute: 是否自动执行
    """
    try:
        database = influxdb_config["influxdb_reference_data"]["database"]

        # 生成ai_energy_saving_reference数据点
        reference_points = generate_optimization_result_points(
            uid_config, optimization_result, "ai_energy_saving_reference", is_auto_execute
        )

        # 写入reference_data_client
        writing_data_to_influxdb(reference_data_client, database, reference_points)

    except Exception as e:
        raise Exception(f"写入ai_energy_saving_reference数据时发生错误: {str(e)}")