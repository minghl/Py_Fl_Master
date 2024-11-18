from flask import Blueprint, request, jsonify
import pandas as pd
import os
import numpy as np
import rpy2.robjects as robjects
from rpy2.robjects.packages import importr
from rpy2.robjects import pandas2ri
from collections import Counter
from scipy.stats import entropy
import random
import json
from diffprivlib.tools import mean
import numpy as np
import pandas as pd
from scipy.stats import entropy
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance
from collections import Counter


bp = Blueprint('main', __name__)

pandas2ri.activate()

sdcmicro = importr('sdcMicro')

def apply_generalization(dataframe, hierarchy_rules):
    generalized_df = dataframe.copy()
        
    print(generalized_df.dtypes)
        
    for qi, rule in hierarchy_rules.items():
        method = rule.get('method', '').lower()

        if method == 'ordering':
            try:
                generalized_df[qi] = pd.to_numeric(generalized_df[qi], errors='coerce')
            except Exception as e:
                print(f"Error converting {qi} to numeric: {e}")
                return None
            
            layers = rule.get('layers', [])
            for layer in layers:
                try:
                    min_val = float(layer['min'])  
                    max_val = float(layer['max'])  
                except ValueError as ve:
                    print(f"Error converting min or max to float in layer: {layer}")
                    return None
                
                label = f"{min_val}-{max_val}"
                
                print(f"Processing layer: min={min_val}, max={max_val}, label={label}")
                print(f"Column {qi} values (first 5 rows):\n{generalized_df[qi].head()}")

                def check_value(x):
                    if pd.notna(x) and isinstance(x, (int, float)):
                        return label if min_val <= x <= max_val else x
                    else:
                        return x
                
                generalized_df[qi] = generalized_df[qi].apply(check_value)
            
            if generalized_df[qi].isna().sum() > 0:
                print(f"Warning: {qi} column contains NaN values after conversion.")
        

        elif method == 'dates':
            try:
                generalized_df[qi] = pd.to_datetime(generalized_df[qi], errors='coerce')
            except Exception as e:
                print(f"Error converting {qi} to datetime: {e}")
                return None
            
            layers = rule.get('layers', [])
            for layer in layers:
                min_date = pd.to_datetime(layer['min'])
                max_date = pd.to_datetime(layer['max'])
                label = f"{min_date.strftime('%Y-%m-%d')} - {max_date.strftime('%Y-%m-%d')}"
                
                print(f"min_date: {min_date}, max_date: {max_date}, label: {label}")

                def check_date_value(x):
                    if pd.notna(x) and isinstance(x, pd.Timestamp):
                        return label if min_date <= x <= max_date else x
                    else:
                        return x
                
                generalized_df[qi] = generalized_df[qi].apply(check_date_value)
            
            if generalized_df[qi].isna().sum() > 0:
                print(f"Warning: {qi} column contains NaN values after conversion.")

        elif method == 'masking':
            masking_string = rule.get('maskingString', 'Masked')
            
            num_stars = masking_string.count('*')
            non_masked_part = masking_string.replace('*', '')
            
            def apply_masking(value):
                if value is None or pd.isna(value):
                    return 'Masked'
                value_str = str(value)
                if len(value_str) <= len(non_masked_part):
                    return '*' * len(value_str)
                return value_str[:len(non_masked_part)] + '*' * num_stars
            
            generalized_df[qi] = generalized_df[qi].apply(apply_masking)
                
        elif method == 'category':
            unique_values = dataframe[qi].unique()
            
            hierarchy = {val: f"{val}" for i, val in enumerate(unique_values) if pd.notna(val)}
            hierarchy['Masked'] = "Unknown"
            
            generalized_df[qi] = generalized_df[qi].map(hierarchy)

    print(generalized_df.head())
    return generalized_df



# def check_m_diversity(group, sensitive_column, m_value):
#     # 使用 Counter 计算敏感列中每个唯一值的出现次数
#     sensitive_values = group[sensitive_column].values
#     value_counts = Counter(sensitive_values)
#     # 返回是否有至少 m 个不同的敏感属性值
#     return len(value_counts) >= m_value

def apply_km_anonymity_r(dataframe, quasi_identifiers, sensitive_column, k_value, m_value,hierarchy_rules,suppression_threshold):
    generalized_df = apply_generalization(dataframe, hierarchy_rules)
    print(generalized_df.head())

    equivalence_class_size = generalized_df.groupby(quasi_identifiers).size().reset_index(name='class_size')

    generalized_df = generalized_df.merge(equivalence_class_size, on=quasi_identifiers)

    small_classes_df = generalized_df[generalized_df['class_size'] < k_value]

    num_to_delete = int(len(small_classes_df) * suppression_threshold)
    
    indices_to_drop = small_classes_df.sample(num_to_delete, random_state=42).index

    anonymized_df = generalized_df.drop(indices_to_drop).drop(columns=['class_size'])
    non_compliant_indices = []

    for _, group in anonymized_df.groupby(quasi_identifiers):
        value_counts = group[sensitive_column].value_counts(normalize=True)
        if any(freq > 1 / m_value for freq in value_counts):
            non_compliant_indices.extend(group.index)

    if non_compliant_indices:
        num_to_delete_km = int(len(non_compliant_indices) * suppression_threshold)
        drop_indices_km = pd.Index(non_compliant_indices).to_series().sample(num_to_delete_km, random_state=42).index
        anonymized_df = anonymized_df.drop(drop_indices_km)

    print(anonymized_df.head())
    
    return anonymized_df

# def apply_km_anonymity_r(dataframe, quasi_identifiers, sensitive_column, k_value, m_value, hierarchy_rules):
#     try:
#         # 确保 quasi_identifiers 是一个列表并转换为字符串
#         quasi_identifiers = [str(qi) for qi in quasi_identifiers] if isinstance(quasi_identifiers, (np.ndarray, list)) else [str(quasi_identifiers)]

#         # 第一步：生成通用化后的数据
#         generalized_df = apply_generalization(dataframe, hierarchy_rules)  # 应用前端传来的分层规则

#         print(f"Generalized DataFrame before R processing (k={k_value}):")
#         print(generalized_df.dtypes)  # 输出每列的数据类型，确保没有 numpy.ndarray
#         print(generalized_df.head())
#         sensitive_column=sensitive_column[0]
#         print(sensitive_column)
#         # 确保 quasi_identifiers 是字符串列表，而不是数组
#         print(f"Quasi Identifiers: {quasi_identifiers}")

#         # 转换为 R 的数据格式
#         r_dataframe = pandas2ri.py2rpy(generalized_df)
#         quasi_identifiers_r = robjects.StrVector(quasi_identifiers)

#         # 使用 sdcMicro 进行 k-匿名处理
#         sdc_obj = sdcmicro.createSdcObj(dat=r_dataframe, keyVars=quasi_identifiers_r)
#         anonymized_sdc = sdcmicro.localSuppression(sdc_obj, k=k_value)

#         # 提取匿名化后的数据
#         anonymized_data = robjects.r['extractManipData'](anonymized_sdc)
#         anonymized_df = pandas2ri.rpy2py(anonymized_data)

#         print(f"Anonymized DataFrame from R (k={k_value}):")
#         print(anonymized_df.head())

#         # 第二步：检查 m-多样性
#         # 根据 quasi_identifiers 进行分组，并检查每个组的敏感属性是否满足 m-多样性
#         km_anonymized_groups = []
#         for _, group in anonymized_df.groupby(quasi_identifiers):  # 确保 quasi_identifiers 是列表
#             # 检查每个组是否满足 k-匿名性和 m-多样性
#             if len(group) >= k_value and check_m_diversity(group, sensitive_column, m_value):
#                 km_anonymized_groups.append(group)
#             else:
#                 # 如果不满足 m-多样性，可以进一步泛化或抑制处理
#                 print(f"Group does not meet m-diversity (m={m_value}), additional suppression required.")

#         # 将满足 km-匿名性和 m-多样性的组重新合并为最终结果
#         if km_anonymized_groups:
#             km_anonymized_df = pd.concat(km_anonymized_groups)
#         else:
#             km_anonymized_df = pd.DataFrame()  # 如果没有满足条件的组

#         print(f"KM-Anonymized DataFrame (k={k_value}, m={m_value}):")
#         print(km_anonymized_df.head())

#         return km_anonymized_df

#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return None

# def apply_k_anonymity_r(dataframe, quasi_identifiers, k_value, hierarchy_rules,suppression_threshold):
#     try:
#         # 第一步：使用前端提供的分层规则进行泛化
#         generalized_df = apply_generalization(dataframe, hierarchy_rules)

#         print(f"{generalized_df}R 处理前的泛化数据框 (k={k_value}):")
#         print(generalized_df.head())

#         # 记录原始数据中的 NaN 位置
#         original_nan_mask = generalized_df[quasi_identifiers].isna()

#         # 转换为 R 数据框格式
#         r_dataframe = pandas2ri.py2rpy(generalized_df)
#         quasi_identifiers_r = robjects.StrVector(quasi_identifiers)

#         # 使用 sdcMicro 进行 k-匿名处理
#         sdc_obj = sdcmicro.createSdcObj(dat=r_dataframe, keyVars=quasi_identifiers_r)
#         anonymized_sdc = sdcmicro.localSuppression(sdc_obj, k=k_value)

#         # 提取匿名化后的数据
#         anonymized_data = robjects.r['extractManipData'](anonymized_sdc)
#         anonymized_df = pandas2ri.rpy2py(anonymized_data)
#         print(f"小等价类总行数: {len(anonymized_df)}, 删除总数: {int(len(anonymized_df) * suppression_threshold)} 数据{anonymized_df}")
#         # 第二步：移除 quasi-identifiers 中含有 'Masked' 或空值的行
#         mask = anonymized_df[quasi_identifiers].apply(lambda x: x.str.contains("Masked", na=False)) | anonymized_df[quasi_identifiers].isna()

#         # 删除任何 quasi-identifier 为 'Masked' 或 NaN 的行
#         anonymized_df = anonymized_df[~mask.any(axis=1)]

# # 计算等价类的大小
#         equivalence_class_size = anonymized_df.groupby(quasi_identifiers).size()
#         small_classes = equivalence_class_size[equivalence_class_size < k_value].index

#         # 获取所有小等价类的行索引
#         small_class_rows = anonymized_df[anonymized_df[quasi_identifiers].apply(tuple, axis=1).isin(small_classes)]
        
#         # 计算要删除的总行数
#         num_to_delete = int(len(small_class_rows) * suppression_threshold)
#         print(f"小等价类总行数: {len(small_class_rows)}, 删除总数: {num_to_delete}")

#         # 随机选择要删除的行索引
#         indices_to_drop = small_class_rows.sample(num_to_delete, random_state=42).index

#         # 删除指定比例的行
#         anonymized_df = anonymized_df.drop(indices_to_drop)

#         print(f"经过 R 处理后 (k={k_value}) 的匿名数据框，移除了小于 k 的等价类中 {suppression_threshold*100}% 的行:")
#         print(anonymized_df.head())
#         return anonymized_df
    
#     except Exception as e:
#         print(f"发生错误: {e}")
#         return None
    
def apply_k_anonymity_r(dataframe, quasi_identifiers, k_value, hierarchy_rules, suppression_threshold):
    generalized_df = apply_generalization(dataframe, hierarchy_rules)
    print(generalized_df.head())

    equivalence_class_size = generalized_df.groupby(quasi_identifiers).size().reset_index(name='class_size')

    generalized_df = generalized_df.merge(equivalence_class_size, on=quasi_identifiers)
    print(generalized_df,'111',equivalence_class_size) 
    small_classes_df = generalized_df[generalized_df['class_size'] < k_value]

    num_to_delete = int(len(small_classes_df) * suppression_threshold)
    
    indices_to_drop = small_classes_df.sample(num_to_delete, random_state=42).index

    anonymized_df = generalized_df.drop(indices_to_drop).drop(columns=['class_size'])

    print(anonymized_df.head())
    
    return anonymized_df

# def apply_t_closeness_r(dataframe, quasi_identifiers, sensitive_attribute, k_value, t_value, hierarchy_rules):
#     try:
#         # Step 1: Apply k-anonymity as the base for t-closeness
#         generalized_df = apply_generalization(dataframe, hierarchy_rules)  # 应用分层规则
        
#         print(f"Generalized DataFrame before R processing (k={k_value}):")
#         print(generalized_df.head())

#         sensitive_attribute=sensitive_attribute[0]
#         print(sensitive_attribute)
#         # 记录原始数据中的 NaN 位置
#         original_nan_mask = generalized_df[quasi_identifiers].isna()

#         # Convert to R dataframe format
#         r_dataframe = pandas2ri.py2rpy(generalized_df)
#         quasi_identifiers_r = robjects.StrVector(quasi_identifiers)

#         # Use sdcMicro for k-anonymity
#         sdc_obj = sdcmicro.createSdcObj(dat=r_dataframe, keyVars=quasi_identifiers_r)
#         anonymized_sdc = sdcmicro.localSuppression(sdc_obj, k=k_value)

#         # Extract anonymized data
#         anonymized_data = robjects.r['extractManipData'](anonymized_sdc)
#         anonymized_df = pandas2ri.rpy2py(anonymized_data)

#         # Step 2: Remove rows with 'Masked' or empty values in quasi-identifiers
#         # 重新处理 mask，确保没有歧义
#         mask = anonymized_df[quasi_identifiers].apply(lambda x: x.str.contains("Masked", na=False))
#         mask = mask.any(axis=1) | anonymized_df[quasi_identifiers].isna().any(axis=1)
#         print(f"Mask applied, masked rows count: {mask.sum()}")
#         anonymized_df = anonymized_df[~mask]

#         # Step 3: Implement t-closeness
#         overall_distribution = calculate_distribution(dataframe, sensitive_attribute)

#         equivalence_classes = anonymized_df.groupby(quasi_identifiers)
#         for name, group in equivalence_classes:
#             print(f"Processing equivalence class: {name}")
#             print(f"Group details: {group.head()}")

#             # 确保 sensitive_attribute 的布尔判断正确使用 .any()
#             if group[sensitive_attribute].isna().any():
#                 print(f"Equivalence class {name} has missing values for sensitive attribute. Skipping this class.")
#                 continue

#             # 等价类过小，跳过
#             if len(group) < 2:
#                 print(f"Equivalence class {name} is too small for t-closeness. Skipping this class.")
#                 continue

#             class_distribution = group[sensitive_attribute].value_counts(normalize=True)

#             # 避免空分布的情况
#             if class_distribution.empty:
#                 print(f"Equivalence class {name} has an empty distribution. Masking sensitive attribute.")
#                 anonymized_df.loc[group.index, sensitive_attribute] = 'Masked'
#                 continue

#             # 计算 Wasserstein 距离，确保 distribution 是 numpy 数组
#             distance = wasserstein_distance(
#                 overall_distribution.values, 
#                 class_distribution.values
#             )
#             print(f"t-closeness distance for class {name}: {distance}")

#             # 如果距离超过 t 值，进行掩码处理
#             if distance > t_value:
#                 print(f"Equivalence class {name} exceeds t-closeness threshold (t={t_value}), masking sensitive attribute.")
#                 anonymized_df.loc[group.index, sensitive_attribute] = 'Masked'

#         # Step 4: Remove rows with 'Masked' values in sensitive attribute after t-closeness processing
#         anonymized_df = anonymized_df[anonymized_df[sensitive_attribute] != 'Masked']

#         print(f"Anonymized DataFrame after t-closeness processing (k={k_value}, t={t_value}):")
#         print(anonymized_df.head())

#         return anonymized_df

#     except Exception as e:
#         print(f"An error occurred during t-closeness processing: {e}")
#         return None
import pandas as pd

def apply_t_closeness_r(dataframe, quasi_identifiers, sensitive_attribute, k_value, t_value, hierarchy_rules,suppression_threshold):
    try:
        generalized_df = apply_generalization(dataframe, hierarchy_rules)
        print(generalized_df.head())

        equivalence_class_size = generalized_df.groupby(quasi_identifiers).size().reset_index(name='class_size')

        generalized_df = generalized_df.merge(equivalence_class_size, on=quasi_identifiers)

        small_classes_df = generalized_df[generalized_df['class_size'] < k_value]

        num_to_delete = int(len(small_classes_df) * suppression_threshold)
        
        indices_to_drop = small_classes_df.sample(num_to_delete, random_state=42).index

        anonymized_df = generalized_df.drop(indices_to_drop).drop(columns=['class_size'])

        mask = anonymized_df[quasi_identifiers].apply(lambda x: x.str.contains("Masked", na=False)) | anonymized_df[quasi_identifiers].isna()
        anonymized_df = anonymized_df[~mask.any(axis=1)]

        to_remove_indices = set()

        sensitive_attribute = sensitive_attribute[0]
        overall_distribution = calculate_distribution(dataframe, sensitive_attribute)

        equivalence_classes = anonymized_df.groupby(quasi_identifiers)
        for name, group in equivalence_classes:
            print(f"Processing equivalence class: {name}")

            if group[sensitive_attribute].isna().sum() > 0:
                print(f"Equivalence class {name} has missing values for sensitive attribute. Skipping this class.")
                continue 

            if len(group) < 2: 
                continue  
        
            class_distribution = group[sensitive_attribute].value_counts(normalize=True)

            if class_distribution.empty:
                print(f"Equivalence class {name} has an empty distribution. Masking sensitive attribute.")
                anonymized_df.loc[group.index, sensitive_attribute] = 'Masked'
                continue 

            distance = wasserstein_distance(overall_distribution, class_distribution)
            print(f"t-closeness distance for class {name}: {distance}")

            if distance > t_value:
                print(f"Equivalence class {name} exceeds t-closeness threshold (t={t_value}), masking sensitive attribute.")
                to_remove_indices.update(group.index)


        num_to_delete = int(len(to_remove_indices) * suppression_threshold)
        print(111)
        indices_to_delete = random.sample(list(to_remove_indices), num_to_delete)
        print(222)
        anonymized_df = anonymized_df.drop(index=indices_to_delete)

        print(f"Anonymized DataFrame after t-closeness processing (k={k_value}, t={t_value}):")
        print(anonymized_df.head())

        return anonymized_df

    except Exception as e:
        print(f"An error occurred during t-closeness processing: {e}")
        return None

def calculate_distribution(dataframe, sensitive_attribute):
    return dataframe[sensitive_attribute].value_counts(normalize=True)

def calculate_kl_divergence(p, q):
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    
    return entropy(p, q)

# def apply_t_closeness_r(dataframe, quasi_identifiers, sensitive_attribute, k_value, t_value, hierarchy_rules, suppression_threshold):
#     # Step 1: 数据泛化 - 调用泛化函数
#     generalized_df = apply_generalization(dataframe, hierarchy_rules)
#     print("泛化后的数据框:")
#     print(generalized_df.head())

#     # Step 2: 计算等价类大小，确保满足 k-anonymity
#     equivalence_class_size = generalized_df.groupby(quasi_identifiers).size().reset_index(name='class_size')
#     generalized_df = generalized_df.merge(equivalence_class_size, on=quasi_identifiers)

#     # Step 3: 过滤小等价类，确保满足 k-anonymity
#     anonymized_df = generalized_df[generalized_df['class_size'] >= k_value].drop(columns=['class_size'])

#     # Step 4: 计算全局敏感属性的分布
#     global_distribution = anonymized_df[sensitive_attribute].value_counts(normalize=True)

#     # Step 1: 收集不满足 t-closeness 的记录索引
#     non_compliant_indices = []  # 用于存储不满足 t-closeness 的记录索引

#     for _, group in anonymized_df.groupby(quasi_identifiers):
#         # 计算当前等价类中敏感属性的分布
#         group_distribution = group[sensitive_attribute].value_counts(normalize=True)

#         # 计算等价类分布与全局分布的差异
#         distance = sum(abs(global_distribution.get(value, 0) - group_distribution.get(value, 0)) for value in global_distribution.index)
        
#         if distance > t_value:
#             # 若不满足 t-closeness，将不满足的组的索引添加到集合中
#             non_compliant_indices.extend(group.index)

#     # Step 2: 根据 suppression_threshold 从不满足的记录中删除一定比例的记录
#     if non_compliant_indices:
#         num_to_delete_t = int(len(non_compliant_indices) * suppression_threshold)
#         drop_indices_t = pd.Index(non_compliant_indices).to_series().sample(num_to_delete_t, random_state=42).index
#         anonymized_df = anonymized_df.drop(drop_indices_t)

#     print(f"应用 k-anonymity (k={k_value}) 和 t-closeness (t={t_value}) 后的匿名数据框:")
#     print(anonymized_df.head())
    
#     return anonymized_df

# def apply_l_diversity_r(dataframe, quasi_identifiers, sensitive_attribute, k_value, l_value, hierarchy_rules):
#     try:
#         # Step 1: 应用分层规则，生成通用化后的数据
#         generalized_df = apply_generalization(dataframe, hierarchy_rules)

#         print(f"Generalized DataFrame before R processing (k={k_value}, l={l_value}):")
#         print(generalized_df.head())

#         # 记录原始数据中的 NaN 位置
#         original_nan_mask = generalized_df[quasi_identifiers].isna()

#         # Step 2: 转换为 R 数据格式，进行 k-匿名处理
#         r_dataframe = pandas2ri.py2rpy(generalized_df)
#         quasi_identifiers_r = robjects.StrVector(quasi_identifiers)

#         # 使用 sdcMicro 进行 k-anonymity
#         sdc_obj = sdcmicro.createSdcObj(dat=r_dataframe, keyVars=quasi_identifiers_r)
#         anonymized_sdc = sdcmicro.localSuppression(sdc_obj, k=k_value)

#         # 提取匿名化后的数据
#         anonymized_data = robjects.r['extractManipData'](anonymized_sdc)
#         anonymized_df = pandas2ri.rpy2py(anonymized_data)

#         # Step 3: 删除准标识符中包含 'Masked' 或 NaN 值的行
#         mask = anonymized_df[quasi_identifiers].apply(lambda x: x.str.contains("Masked", na=False)) | anonymized_df[quasi_identifiers].isna()
#         anonymized_df = anonymized_df[~mask.any(axis=1)]

#         # Step 4: 删除不满足 k-匿名性的记录
#         equivalence_class_size = anonymized_df.groupby(quasi_identifiers).size()

#         # 找到小于 k 的等价类
#         small_classes = equivalence_class_size[equivalence_class_size < k_value].index

#         # 删除这些小等价类对应的行
#         anonymized_df = anonymized_df[~anonymized_df[quasi_identifiers].apply(tuple, axis=1).isin(small_classes)]

#         # Step 5: 检查 l-diversity 约束
#         equivalence_classes = anonymized_df.groupby(quasi_identifiers)

#         # 检查每个等价类的 l-diversity
#         for name, group in equivalence_classes:
#             sensitive_values = group[sensitive_attribute]
#             print(f"{group}{sensitive_attribute}")
#             # 如果敏感值的数量小于 l，则删除这些行
#             if len(sensitive_values) < l_value:
#                 anonymized_df = anonymized_df.drop(group.index)

#         print(f"Anonymized DataFrame (k={k_value}, l={l_value}) after applying l-diversity:")
#         print(anonymized_df.head())

#         return anonymized_df

#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return None

def apply_l_diversity_r(dataframe, quasi_identifiers, sensitive_attribute, k_value, l_value, hierarchy_rules, suppression_threshold):
    generalized_df = apply_generalization(dataframe, hierarchy_rules)
    print("泛化后的数据框:")
    print(generalized_df.head())

    equivalence_class_size = generalized_df.groupby(quasi_identifiers).size().reset_index(name='class_size')

    generalized_df = generalized_df.merge(equivalence_class_size, on=quasi_identifiers)

    small_classes_df = generalized_df[generalized_df['class_size'] < k_value]

    num_to_delete = int(len(small_classes_df) * suppression_threshold)
    
    indices_to_drop = small_classes_df.sample(num_to_delete, random_state=42).index

    anonymized_df = generalized_df.drop(indices_to_drop).drop(columns=['class_size'])

    sensitive_attribute = sensitive_attribute[0]
    non_compliant_indices = []  
    for _, group in anonymized_df.groupby(quasi_identifiers):
        unique_sensitive_values_count = group[sensitive_attribute].nunique()
        print(unique_sensitive_values_count, 'sssss', group)

        if unique_sensitive_values_count < l_value:
            non_compliant_indices.extend(group.index)

    if non_compliant_indices:
        num_to_delete_l = int(len(non_compliant_indices) * suppression_threshold)
        drop_indices_l = pd.Index(non_compliant_indices).to_series().sample(num_to_delete_l, random_state=42).index
        anonymized_df = anonymized_df.drop(drop_indices_l)

    print(anonymized_df.head())
    
    return anonymized_df


# def apply_differential_privacy(dataframe, epsilon, delta, quasi_identifiers, sensitive_columns, hierarchy_rules, budget, suppression_threshold):
#     try:
#         # 创建一个新的 DataFrame 用于存储差分隐私处理后的数据
#         anonymized_df = dataframe.copy()
        
#         # 使用传入的预算
#         privacy_budget = budget / len(quasi_identifiers)  # 按 quasi_identifiers 平分预算

#         for qi in quasi_identifiers:
#             if qi in dataframe.columns:
#                 # 检查数据类型
#                 rule = hierarchy_rules.get(qi, None)

#                 if rule and rule.get('method') == 'dates':
#                     days_since_epoch = (pd.to_datetime(dataframe[qi], errors='coerce') - pd.Timestamp("1970-01-01")) // pd.Timedelta('1D')
                    
#                     # 添加噪声，使用 epsilon 和预算
#                     noise = np.random.laplace(0, 1/(epsilon * privacy_budget), size=days_since_epoch.shape)
#                     noisy_days = days_since_epoch + noise
                    
#                     # 将时间戳转换回日期格式
#                     anonymized_df[qi] = pd.to_datetime(noisy_days, origin='1970-01-01', unit='D').dt.date
#                     anonymized_df[qi] = anonymized_df[qi].astype(str)
                    
#                     # 层次分组的处理
#                     layers = rule.get('layers', [])
#                     for layer in layers:
#                         min_date = pd.to_datetime(layer['min'])
#                         max_date = pd.to_datetime(layer['max'])
#                         label = f"{min_date.strftime('%Y-%m-%d')} - {max_date.strftime('%Y-%m-%d')}"
#                         # 确保 min_date 和 max_date 没有时区
#                         min_date = min_date.tz_localize(None)
#                         max_date = max_date.tz_localize(None)

#                         # 对每个值进行分组，确保日期值不超出层次分组的范围
#                         anonymized_df[qi] = anonymized_df[qi].apply(
#                             lambda x: label if pd.notna(pd.to_datetime(x, errors='coerce').tz_localize(None)) 
#                                     and min_date <= pd.to_datetime(x, errors='coerce').tz_localize(None) <= max_date else x
#                         )
#                 elif rule and rule.get('method') == 'ordering' and np.issubdtype(dataframe[qi].dtype, np.number):
#                     # 对数值型数据应用差分隐私
#                     column_data = pd.to_numeric(dataframe[qi], errors='coerce')
#                     column_data = column_data.dropna()  # 删除空值
                    
#                     layers = rule.get('layers', [])
#                     for layer in layers:
#                         try:
#                             min_val = float(layer['min'])
#                             max_val = float(layer['max'])
#                         except ValueError as ve:
#                             print(f"Error converting min or max to float in layer: {layer}")
#                             return None
                        
#                         label = f"{min_val}-{max_val}"
                        
#                         def try_float(x):
#                             try:
#                                 return float(x)
#                             except (ValueError, TypeError):  # 捕获类型错误和转换错误
#                                 return None  # 如果无法转换，返回 None

#                         anonymized_df[qi] = anonymized_df[qi].apply(lambda x: label if try_float(x) is not None and min_val <= try_float(x) <= max_val else x)
#                         # anonymized_df[qi] = anonymized_df[qi].apply(lambda x: label if min_val <= x <= max_val else x)

#                     if anonymized_df[qi].isna().sum() > 0:
#                         print(f"Warning: {qi} column contains NaN values after conversion.")

#                 elif rule and rule.get('method') == 'category':
#                     # 对类别数据应用分层规则
#                     unique_categories = dataframe[qi].unique()

#                         # 创建类别映射，映射到不同的类型
#                     category_mapping = {val: f"{val}" for i, val in enumerate(unique_categories)}
                    
#                     # 只映射到原始的类别，不生成新的类别
#                     anonymized_df[qi] = dataframe[qi].map(category_mapping).fillna('Unknown')
#                 elif rule and rule.get('method') == 'masking':
#                     masking_string = rule.get('maskingString', '***')
#                     num_stars = masking_string.count('*')
#                     non_masked_part = masking_string.replace('*', '')

#                     def mask_value(value):
#                         value_str = str(value)
#                         if len(value_str) <= len(non_masked_part):
#                             return '*' * len(value_str)
#                         return value_str[:len(non_masked_part)] + '*' * num_stars
                    
#                     anonymized_df[qi] = dataframe[qi].apply(mask_value)

#                 else:
#                     print(f"Column '{qi}' does not match any known rule. Skipping this column.")
        
#         print(f"Warning: {sensitive_columns}")

#         # Suppression logic (if necessary)
#         print(len(anonymized_df),'111111')
#         anonymized_df = anonymized_df.applymap(lambda x: None if np.random.rand() < suppression_threshold else x)
#         # anonymized_df.dropna(inplace=True)

#         print(f"Differentially Private DataFrame (epsilon={epsilon}, delta={delta}):")
#         print(anonymized_df.head())

#         return anonymized_df

#     except Exception as e:
#         import traceback
#         print("Full traceback of the error:")
#         traceback.print_exc()
#         raise



def read_file(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == '.csv':
        return pd.read_csv(file_path)
    elif file_extension == '.tsv':
        return pd.read_csv(file_path, sep='\t')
    else:
        raise ValueError("Unsupported file format. Please use a .csv or .tsv file.")

# def clean_columns(dataframe):
#     # 尝试将 max_glu_serum 和 A1Cresult 转换为数值类型，无法转换的部分将被设置为 NaN
#     dataframe['max_glu_serum'] = pd.to_numeric(dataframe['max_glu_serum'], errors='coerce')
#     dataframe['A1Cresult'] = pd.to_numeric(dataframe['A1Cresult'], errors='coerce')
#     return dataframe

# # 然后在 apply_generalization 之前调用 clean_columns
# dataPd = clean_columns(dataPd)


@bp.route('/anonymize', methods=['POST'])
def anonymize():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    privacy_model = request.form.get('privacy_model', 'k-anonymity')
    k_value = request.form.get('k', None)
    if k_value:
        k_value = int(k_value)
    
    l_value = request.form.get('l', None)
    if l_value:
        l_value = int(l_value)
    
    t_value = request.form.get('t', None)
    if t_value:
        t_value = float(t_value)
    
    m_value = request.form.get('m', None)
    if m_value:
        m_value = float(m_value)

    epsilon = request.form.get('e', None)
    if epsilon:
        epsilon = float(epsilon)


    quasi_identifiers = request.form.get('quasi_identifiers', 'Gender,Age,Zipcode').split(',')
    sensitive_column = request.form.get('sensitive_column', 'Disease').split(',')
    
    hierarchy_rules = json.loads(request.form.get('hierarchy_rules', '{}'))
    
    file_path = os.path.join(bp.root_path, 'uploads', file.filename)
    suppression_threshold = float(request.form.get('suppression_threshold', '0.3'))  # 抑制阈值
    file.save(file_path)
    dataPd = read_file(file_path)

    for qi in quasi_identifiers:
        if qi not in dataPd.columns:
            return jsonify({'error': f"Column '{qi}' does not exist in the file."}), 400

    try:
        if privacy_model == 'k-anonymity':
            resultPd = apply_k_anonymity_r(dataPd, quasi_identifiers, k_value, hierarchy_rules,suppression_threshold)
            if resultPd is None:
                raise ValueError("Anonymization process returned no result.")
            return resultPd.to_json(orient='records')
        
        elif privacy_model == 'l-diversity':
            resultPd = apply_l_diversity_r(dataPd, quasi_identifiers, sensitive_column, k_value,l_value, hierarchy_rules,suppression_threshold)
            if resultPd is None:
                return jsonify({'error': 'Failed to apply l-diversity.'}), 400
            return resultPd.to_json(orient='records')
        
        elif privacy_model == 't-closeness':
            resultPd = apply_t_closeness_r(dataPd, quasi_identifiers, sensitive_column, k_value, t_value, hierarchy_rules,suppression_threshold)
            if resultPd is None:
                return jsonify({'error': 'Failed to apply t-closeness.'}), 400
            return resultPd.to_json(orient='records')
        
        elif privacy_model == 'km-anonymity':
            resultPd = apply_km_anonymity_r(dataPd, quasi_identifiers, sensitive_column,k_value, m_value, hierarchy_rules,suppression_threshold)
            if resultPd is None:
                return jsonify({'error': 'Failed to apply km-closeness.'}), 400
            return resultPd.to_json(orient='records')
        
        # elif privacy_model == 'differential_privacy':
        #     if not epsilon:
        #         return jsonify({'error': 'Epsilon value is required for differential privacy'}), 400
        #     delta = request.form.get('delta', '1e-6')  # 默认delta为1e-6
        #     budget = request.form.get('budget', '100')  # 默认预算为100%
        #     resultPd = apply_differential_privacy(dataPd, epsilon, float(delta), quasi_identifiers, sensitive_column,hierarchy_rules, float(budget), suppression_threshold)
        #     return resultPd.to_json(orient='records')
        
        else:
            return jsonify({'error': f"Unsupported privacy model: {privacy_model}"}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Unable to convert: {str(e)}"}), 400
