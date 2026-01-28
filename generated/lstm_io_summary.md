# LSTM 输入/输出整理

说明：此文件基于 mapping 配置整理 LSTM 使用的输入/输出 UID 列表。

## 103A_modeling

- 输出（targets）：66 个传感器 UID（预测 t+horizon）
- 输入（features）：空调设定/特征点 + 额外特征 + 列头柜 + 传感器历史状态（state_{uid}，含 target-lags）

### 输出：sensors
| uid | name | tag | category |
| --- | --- | --- | --- |
| a7217828_ed16_4ffa_b789_04ada92a2e75 | 1F IDC机房热通道33#温湿度 | 1#温度 | temp_humidity_sensor |
| 52664cb3_a254_46c0_9674_777ef3b68793 | 1F IDC机房热通道33#温湿度 | 1#湿度 | temp_humidity_sensor |
| a38944a0_b951_45b2_a13c_13a6fa9223e4 | 1F IDC机房冷通道32#温湿度 | 1#温度 | temp_humidity_sensor |
| 600edf85_f3ec_46e5_a811_855f82ae07f4 | 1F IDC机房冷通道32#温湿度 | 1#湿度 | temp_humidity_sensor |
| 4fe07996_cd59_4771_ab80_bab15210849b | 1F IDC机房热通道31#温湿度 | 1#温度 | temp_humidity_sensor |
| b111676c_bfed_4fca_a23e_91774e9736fa | 1F IDC机房热通道31#温湿度 | 1#湿度 | temp_humidity_sensor |
| 44686a4e_336a_471f_9f04_abfe29f12c8a | 1F IDC机房冷通道30#温湿度 | 1#温度 | temp_humidity_sensor |
| 24e69074_556e_421e_88bc_d983f21e2a46 | 1F IDC机房冷通道30#温湿度 | 1#湿度 | temp_humidity_sensor |
| 0ab54859_d564_4e3d_9810_2d74a26d007d | 1F IDC机房热通道29#温湿度 | 1#温度 | temp_humidity_sensor |
| 25c42ff2_2278_42ca_b97c_43f82cf29737 | 1F IDC机房热通道29#温湿度 | 1#湿度 | temp_humidity_sensor |
| f50dd4c9_c782_4c40_81e6_14dcfd755436 | 1F IDC机房冷通道28#温湿度 | 1#温度 | temp_humidity_sensor |
| dd6f7451_7a3d_4656_97ef_b350af38491a | 1F IDC机房冷通道28#温湿度 | 1#湿度 | temp_humidity_sensor |
| bdb38c2a_f0c6_49c0_b62a_d4e0fc5fd0ea | 1F IDC机房热通道27#温湿度 | 1#温度 | temp_humidity_sensor |
| b3582d8f_390a_4db6_8f42_68be2cad1339 | 1F IDC机房热通道27#温湿度 | 1#湿度 | temp_humidity_sensor |
| a10310ed_ff3a_4bdf_b02e_0362f5808958 | 1F IDC机房冷通道26#温湿度 | 1#温度 | temp_humidity_sensor |
| 0dc718ed_ea4c_4d82_be43_6d94b9943fa7 | 1F IDC机房冷通道26#温湿度 | 1#湿度 | temp_humidity_sensor |
| 07bb7d1d_b635_4ca9_909c_7bdaf3ceab10 | 1F IDC机房热通道25#温湿度 | 1#温度 | temp_humidity_sensor |
| e8700958_d7b7_4050_874d_294fbe149531 | 1F IDC机房热通道25#温湿度 | 1#湿度 | temp_humidity_sensor |
| be578260_b5e1_4e29_888f_4ba9d2c1b138 | 1F IDC机房冷通道24#温湿度 | 1#温度 | temp_humidity_sensor |
| 8e318fc0_0003_43c3_8817_0920307d4e1a | 1F IDC机房冷通道24#温湿度 | 1#湿度 | temp_humidity_sensor |
| ad0a96f7_8d56_4120_b0fd_666f6419da54 | 1F IDC机房热通道23#温湿度 | 1#温度 | temp_humidity_sensor |
| 50811f02_536c_4bdb_88f7_1769d6110ea1 | 1F IDC机房热通道23#温湿度 | 1#湿度 | temp_humidity_sensor |
| N2_S0_E102_A1 | 1F IDC机房热通道22#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E102_A2 | 1F IDC机房热通道22#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E101_A1 | 1F IDC机房热通道21#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E101_A2 | 1F IDC机房热通道21#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E100_A1 | 1F IDC机房冷通道20#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E100_A2 | 1F IDC机房冷通道20#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E99_A1 | 1F IDC机房冷通道19#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E99_A2 | 1F IDC机房冷通道19#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E98_A1 | 1F IDC机房热通道18#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E98_A2 | 1F IDC机房热通道18#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E97_A1 | 1F IDC机房热通道17#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E97_A2 | 1F IDC机房热通道17#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E96_A1 | 1F IDC机房冷通道16#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E96_A2 | 1F IDC机房冷通道16#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E95_A1 | 1F IDC机房冷通道15#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E95_A2 | 1F IDC机房冷通道15#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E94_A1 | 1F IDC机房热通道14#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E94_A2 | 1F IDC机房热通道14#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E93_A1 | 1F IDC机房热通道13#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E93_A2 | 1F IDC机房热通道13#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E92_A1 | 1F IDC机房冷通道12#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E92_A2 | 1F IDC机房冷通道12#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E91_A1 | 1F IDC机房冷通道11#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E91_A2 | 1F IDC机房冷通道11#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E90_A1 | 1F IDC机房热通道10#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E90_A2 | 1F IDC机房热通道10#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E89_A1 | 1F IDC机房热通道9#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E89_A2 | 1F IDC机房热通道9#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E88_A1 | 1F IDC机房冷通道8#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E88_A2 | 1F IDC机房冷通道8#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E87_A1 | 1F IDC机房冷通道7#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E87_A2 | 1F IDC机房冷通道7#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E86_A1 | 1F IDC机房热通道6#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E86_A2 | 1F IDC机房热通道6#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E85_A1 | 1F IDC机房热通道5#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E85_A2 | 1F IDC机房热通道5#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E84_A1 | 1F IDC机房冷通道4#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E84_A2 | 1F IDC机房冷通道4#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E83_A1 | 1F IDC机房冷通道3#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E83_A2 | 1F IDC机房冷通道3#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E82_A1 | 1F IDC机房热通道2#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E82_A2 | 1F IDC机房热通道2#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E81_A1 | 1F IDC机房热通道1#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E81_A2 | 1F IDC机房热通道1#温湿度 | 湿度 | temp_humidity_sensor |

### 输入：air_conditioners（空调设定/特征点）
| ac_no | uid | tag |
| --- | --- | --- |
| 1 | N2_S0_E1_A26 | 风压设定点（Pa） |
| 1 | N2_S0_E1_A27 | 回风湿度设定点（%） |
| 1 | N2_S0_E1_A28 | 回风温度设定点（℃） |
| 1 | N2_S0_E1_A30 | 远程平均温度设定点（℃） |
| 1 | N2_S0_E1_A31 | 远程最高温度设定点（℃） |
| 2 | N2_S0_E2_A26 | 风压设定点（Pa） |
| 2 | N2_S0_E2_A27 | 回风湿度设定点（%） |
| 2 | N2_S0_E2_A28 | 回风温度设定点（℃） |
| 2 | N2_S0_E2_A30 | 远程平均温度设定点（℃） |
| 2 | N2_S0_E2_A31 | 远程最高温度设定点（℃） |
| 3 | N2_S0_E3_A26 | 风压设定点（Pa） |
| 3 | N2_S0_E3_A27 | 回风湿度设定点（%） |
| 3 | N2_S0_E3_A28 | 回风温度设定点（℃） |
| 3 | N2_S0_E3_A30 | 远程平均温度设定点（℃） |
| 3 | N2_S0_E3_A31 | 远程最高温度设定点（℃） |
| 4 | N2_S0_E4_A26 | 风压设定点（Pa） |
| 4 | N2_S0_E4_A27 | 回风湿度设定点（%） |
| 4 | N2_S0_E4_A28 | 回风温度设定点（℃） |
| 4 | N2_S0_E4_A30 | 远程平均温度设定点（℃） |
| 4 | N2_S0_E4_A31 | 远程最高温度设定点（℃） |
| 5 | N2_S0_E5_A26 | 风压设定点（Pa） |
| 5 | N2_S0_E5_A27 | 回风湿度设定点（%） |
| 5 | N2_S0_E5_A28 | 回风温度设定点（℃） |
| 5 | N2_S0_E5_A30 | 远程平均温度设定点（℃） |
| 5 | N2_S0_E5_A31 | 远程最高温度设定点（℃） |
| 6 | N2_S0_E6_A26 | 风压设定点（Pa） |
| 6 | N2_S0_E6_A27 | 回风湿度设定点（%） |
| 6 | N2_S0_E6_A28 | 回风温度设定点（℃） |
| 6 | N2_S0_E6_A30 | 远程平均温度设定点（℃） |
| 6 | N2_S0_E6_A31 | 远程最高温度设定点（℃） |
| 7 | N2_S0_E7_A26 | 风压设定点（Pa） |
| 7 | N2_S0_E7_A27 | 回风湿度设定点（%） |
| 7 | N2_S0_E7_A28 | 回风温度设定点（℃） |
| 7 | N2_S0_E7_A30 | 远程平均温度设定点（℃） |
| 7 | N2_S0_E7_A31 | 远程最高温度设定点（℃） |
| 8 | N2_S0_E8_A26 | 风压设定点（Pa） |
| 8 | N2_S0_E8_A27 | 回风湿度设定点（%） |
| 8 | N2_S0_E8_A28 | 回风温度设定点（℃） |
| 8 | N2_S0_E8_A30 | 远程平均温度设定点（℃） |
| 8 | N2_S0_E8_A31 | 远程最高温度设定点（℃） |
| 9 | N2_S0_E9_A26 | 风压设定点（Pa） |
| 9 | N2_S0_E9_A27 | 回风湿度设定点（%） |
| 9 | N2_S0_E9_A28 | 回风温度设定点（℃） |
| 9 | N2_S0_E9_A30 | 远程平均温度设定点（℃） |
| 9 | N2_S0_E9_A31 | 远程最高温度设定点（℃） |

### 输入：extra_features（额外特征）
| uid | name | tag | category |
| --- | --- | --- | --- |
| 58a917f3_ce9e_4005_bf7c_e15455f4ca9b | 1#放冷泵运行状态码 | None | extra_feature |
| 15efbcdc_9f75_4061_b8c1_cbe1cbc6a430 | 2#放冷泵运行状态码 | None | extra_feature |
| 566185d4_6cac_4dcc_a52a_0b3bece9d920 | 1#冷机冷冻出水温度 | None | extra_feature |
| b1858cac_4abf_4789_8a62_6c1aec8615c6 | 1#冷机冷冻进水温度 | None | extra_feature |
| 2976cfd2_6b50_4bf7_abfc_4d9806c81409 | 1#冷机冷冻水流开关 | None | extra_feature |
| 650186e2_c232_4ad0_a13c_7c572ea1f883 | 2#冷机冷冻出水温度 | None | extra_feature |
| 7479ada1_b9b3_41b4_a3fa_05e3d4969d04 | 2#冷机冷冻进水温度 | None | extra_feature |
| fc863933_4222_4aa8_a536_028a7edc187d | 2#冷机冷冻水流开关 | None | extra_feature |
| 8ff4a8f3_0a2f_486e_b758_2219f1cfbb23 | 3#冷机冷冻出水温度 | None | extra_feature |
| d8f07bad_c577_4b09_96f9_5a989212ddfb | 3#冷机冷冻进水温度 | None | extra_feature |
| 663dd565_fe66_4139_a6af_6b594aab537b | 3#冷机冷冻水流开关 | None | extra_feature |
| abb8c9a3_d5de_437a_9fdc_8219bc851c73 | 4#冷机冷冻出水温度 | None | extra_feature |
| 0d4d1f7d_d7e0_46ff_9779_b92f59b1ab04 | 4#冷机冷冻进水温度 | None | extra_feature |
| ff4bb6aa_86fe_41f7_bd68_8485cbbd14db | 4#冷机冷冻水流开关 | None | extra_feature |

### 输入：cabinets（列头柜）
| uid | name | tag | category |
| --- | --- | --- | --- |
| N2_S0_E40_A63 | 103A信息化机房/1F E列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E40_A62 | 103A信息化机房/1F E列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E40_A61 | 103A信息化机房/1F E列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E39_A9 | 103A信息化机房/1F E列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E39_A8 | 103A信息化机房/1F E列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E39_A7 | 103A信息化机房/1F E列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E38_A63 | 103A信息化机房/1F D列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E38_A62 | 103A信息化机房/1F D列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E38_A61 | 103A信息化机房/1F D列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E37_A9 | 103A信息化机房/1F D列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E37_A8 | 103A信息化机房/1F D列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E37_A7 | 103A信息化机房/1F D列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E36_A63 | 103A信息化机房/1F C列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E36_A62 | 103A信息化机房/1F C列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E36_A61 | 103A信息化机房/1F C列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E35_A9 | 103A信息化机房/1F C列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E35_A8 | 103A信息化机房/1F C列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E35_A7 | 103A信息化机房/1F C列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E34_A63 | 103A信息化机房/1F B列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E34_A62 | 103A信息化机房/1F B列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E34_A61 | 103A信息化机房/1F B列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E33_A9 | 103A信息化机房/1F B列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E33_A8 | 103A信息化机房/1F B列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E33_A7 | 103A信息化机房/1F B列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E32_A63 | 103A信息化机房/1F A列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E32_A62 | 103A信息化机房/1F A列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E32_A61 | 103A信息化机房/1F A列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E31_A9 | 103A信息化机房/1F A列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E31_A8 | 103A信息化机房/1F A列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E31_A7 | 103A信息化机房/1F A列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E190_A63 | 103A信息化机房/1F J列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E190_A62 | 103A信息化机房/1F J列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E190_A61 | 103A信息化机房/1F J列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E189_A9 | 103A信息化机房/1F J列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E189_A8 | 103A信息化机房/1F J列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E189_A7 | 103A信息化机房/1F J列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E188_A63 | 103A信息化机房/1F I列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E188_A62 | 103A信息化机房/1F I列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E188_A61 | 103A信息化机房/1F I列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E187_A9 | 103A信息化机房/1F I列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E187_A8 | 103A信息化机房/1F I列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E187_A7 | 103A信息化机房/1F I列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E186_A63 | 103A信息化机房/1F H列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E186_A62 | 103A信息化机房/1F H列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E186_A61 | 103A信息化机房/1F H列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E185_A9 | 103A信息化机房/1F H列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E185_A8 | 103A信息化机房/1F H列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E185_A7 | 103A信息化机房/1F H列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E184_A63 | 103A信息化机房/1F G列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E184_A62 | 103A信息化机房/1F G列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E184_A61 | 103A信息化机房/1F G列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E183_A9 | 103A信息化机房/1F G列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E183_A8 | 103A信息化机房/1F G列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E183_A7 | 103A信息化机房/1F G列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E182_A63 | 103A信息化机房/1F F列头柜B路.主路2输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E182_A62 | 103A信息化机房/1F F列头柜B路.主路2输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E182_A61 | 103A信息化机房/1F F列头柜B路.主路2输入相电流 A（A） | None | cabinet_feed |
| N2_S0_E181_A9 | 103A信息化机房/1F F列头柜A路.主路1输入相电流 C（A） | None | cabinet_feed |
| N2_S0_E181_A8 | 103A信息化机房/1F F列头柜A路.主路1输入相电流 B（A） | None | cabinet_feed |
| N2_S0_E181_A7 | 103A信息化机房/1F F列头柜A路.主路1输入相电流 A（A） | None | cabinet_feed |

### 输入：传感器历史状态（state_{uid}，用于自回归）
| base_uid | name | tag | category |
| --- | --- | --- | --- |
| a7217828_ed16_4ffa_b789_04ada92a2e75 | 1F IDC机房热通道33#温湿度 | 1#温度 | temp_humidity_sensor |
| 52664cb3_a254_46c0_9674_777ef3b68793 | 1F IDC机房热通道33#温湿度 | 1#湿度 | temp_humidity_sensor |
| a38944a0_b951_45b2_a13c_13a6fa9223e4 | 1F IDC机房冷通道32#温湿度 | 1#温度 | temp_humidity_sensor |
| 600edf85_f3ec_46e5_a811_855f82ae07f4 | 1F IDC机房冷通道32#温湿度 | 1#湿度 | temp_humidity_sensor |
| 4fe07996_cd59_4771_ab80_bab15210849b | 1F IDC机房热通道31#温湿度 | 1#温度 | temp_humidity_sensor |
| b111676c_bfed_4fca_a23e_91774e9736fa | 1F IDC机房热通道31#温湿度 | 1#湿度 | temp_humidity_sensor |
| 44686a4e_336a_471f_9f04_abfe29f12c8a | 1F IDC机房冷通道30#温湿度 | 1#温度 | temp_humidity_sensor |
| 24e69074_556e_421e_88bc_d983f21e2a46 | 1F IDC机房冷通道30#温湿度 | 1#湿度 | temp_humidity_sensor |
| 0ab54859_d564_4e3d_9810_2d74a26d007d | 1F IDC机房热通道29#温湿度 | 1#温度 | temp_humidity_sensor |
| 25c42ff2_2278_42ca_b97c_43f82cf29737 | 1F IDC机房热通道29#温湿度 | 1#湿度 | temp_humidity_sensor |
| f50dd4c9_c782_4c40_81e6_14dcfd755436 | 1F IDC机房冷通道28#温湿度 | 1#温度 | temp_humidity_sensor |
| dd6f7451_7a3d_4656_97ef_b350af38491a | 1F IDC机房冷通道28#温湿度 | 1#湿度 | temp_humidity_sensor |
| bdb38c2a_f0c6_49c0_b62a_d4e0fc5fd0ea | 1F IDC机房热通道27#温湿度 | 1#温度 | temp_humidity_sensor |
| b3582d8f_390a_4db6_8f42_68be2cad1339 | 1F IDC机房热通道27#温湿度 | 1#湿度 | temp_humidity_sensor |
| a10310ed_ff3a_4bdf_b02e_0362f5808958 | 1F IDC机房冷通道26#温湿度 | 1#温度 | temp_humidity_sensor |
| 0dc718ed_ea4c_4d82_be43_6d94b9943fa7 | 1F IDC机房冷通道26#温湿度 | 1#湿度 | temp_humidity_sensor |
| 07bb7d1d_b635_4ca9_909c_7bdaf3ceab10 | 1F IDC机房热通道25#温湿度 | 1#温度 | temp_humidity_sensor |
| e8700958_d7b7_4050_874d_294fbe149531 | 1F IDC机房热通道25#温湿度 | 1#湿度 | temp_humidity_sensor |
| be578260_b5e1_4e29_888f_4ba9d2c1b138 | 1F IDC机房冷通道24#温湿度 | 1#温度 | temp_humidity_sensor |
| 8e318fc0_0003_43c3_8817_0920307d4e1a | 1F IDC机房冷通道24#温湿度 | 1#湿度 | temp_humidity_sensor |
| ad0a96f7_8d56_4120_b0fd_666f6419da54 | 1F IDC机房热通道23#温湿度 | 1#温度 | temp_humidity_sensor |
| 50811f02_536c_4bdb_88f7_1769d6110ea1 | 1F IDC机房热通道23#温湿度 | 1#湿度 | temp_humidity_sensor |
| N2_S0_E102_A1 | 1F IDC机房热通道22#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E102_A2 | 1F IDC机房热通道22#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E101_A1 | 1F IDC机房热通道21#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E101_A2 | 1F IDC机房热通道21#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E100_A1 | 1F IDC机房冷通道20#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E100_A2 | 1F IDC机房冷通道20#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E99_A1 | 1F IDC机房冷通道19#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E99_A2 | 1F IDC机房冷通道19#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E98_A1 | 1F IDC机房热通道18#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E98_A2 | 1F IDC机房热通道18#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E97_A1 | 1F IDC机房热通道17#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E97_A2 | 1F IDC机房热通道17#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E96_A1 | 1F IDC机房冷通道16#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E96_A2 | 1F IDC机房冷通道16#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E95_A1 | 1F IDC机房冷通道15#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E95_A2 | 1F IDC机房冷通道15#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E94_A1 | 1F IDC机房热通道14#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E94_A2 | 1F IDC机房热通道14#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E93_A1 | 1F IDC机房热通道13#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E93_A2 | 1F IDC机房热通道13#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E92_A1 | 1F IDC机房冷通道12#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E92_A2 | 1F IDC机房冷通道12#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E91_A1 | 1F IDC机房冷通道11#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E91_A2 | 1F IDC机房冷通道11#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E90_A1 | 1F IDC机房热通道10#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E90_A2 | 1F IDC机房热通道10#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E89_A1 | 1F IDC机房热通道9#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E89_A2 | 1F IDC机房热通道9#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E88_A1 | 1F IDC机房冷通道8#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E88_A2 | 1F IDC机房冷通道8#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E87_A1 | 1F IDC机房冷通道7#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E87_A2 | 1F IDC机房冷通道7#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E86_A1 | 1F IDC机房热通道6#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E86_A2 | 1F IDC机房热通道6#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E85_A1 | 1F IDC机房热通道5#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E85_A2 | 1F IDC机房热通道5#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E84_A1 | 1F IDC机房冷通道4#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E84_A2 | 1F IDC机房冷通道4#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E83_A1 | 1F IDC机房冷通道3#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E83_A2 | 1F IDC机房冷通道3#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E82_A1 | 1F IDC机房热通道2#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E82_A2 | 1F IDC机房热通道2#温湿度 | 湿度 | temp_humidity_sensor |
| N2_S0_E81_A1 | 1F IDC机房热通道1#温湿度 | 温度 | temp_humidity_sensor |
| N2_S0_E81_A2 | 1F IDC机房热通道1#温湿度 | 湿度 | temp_humidity_sensor |

## chiller_modeling

- 输出（targets）：92 个 output UID（预测 t+horizon）
- 输入（features）：inputs + 输出状态（state_{uid}，用于自回归）

### 输出：outputs
| uid | name | category |
| --- | --- | --- |
| 26aa984f_ddc1_4c33_9c96_b3313aad2a72 | 冷冻总管回水平均温度 | output |
| 4398dbf6_8f98_4222_9f58_4e91feab323d | 蓄冷水池平均温度 | output |
| b1858cac_4abf_4789_8a62_6c1aec8615c6 | 1#冷机冷冻进水温度 | output |
| 8f3102af_f9e3_4a68_b191_bc1a995af0c4 | 1#冷机冷却出水温度 | output |
| 7479ada1_b9b3_41b4_a3fa_05e3d4969d04 | 2#冷机冷冻进水温度 | output |
| 0cce079d_2e85_4711_b973_e9e3b9bc30a3 | 2#冷机冷却出水温度 | output |
| d8f07bad_c577_4b09_96f9_5a989212ddfb | 3#冷机冷冻进水温度 | output |
| 0a9f2a34_183d_4434_b2b4_dc581d25e29a | 3#冷机冷却出水温度 | output |
| 0d4d1f7d_d7e0_46ff_9779_b92f59b1ab04 | 4#冷机冷冻进水温度 | output |
| 3d88232c_0a10_452c_aa67_c8d0737a93a7 | 4#冷机冷却出水温度 | output |
| 7c70b29c_173e_4b3a_9cb7_e49af1206593 | 冷冻回水温度1 | output |
| aa95fde4_879a_468d_9a2a_cbd63121cb68 | 冷冻回水温度2 | output |
| 0a85728b_efa0_42e5_aa27_81c30fb45786 | 1#冷却塔出水温度 | output |
| fa492a03_c5df_42d4_96df_7eef051bb972 | 2#冷却塔出水温度 | output |
| 73c216fa_7de6_4b7a_827b_2b3caaa7ab94 | 3#冷却塔出水温度 | output |
| d712284a_e38f_4433_b507_ca48b5977b42 | 4#冷却塔出水温度 | output |
| 46902447_9fe5_45bc_8f59_e17471cbead8 | 5#冷却塔出水温度 | output |
| 1b1de943_5762_4279_b7dc_7867c706718f | 6#冷却塔出水温度 | output |
| dd80b34a_e30e_4076_9182_ca306c58d890 | 7#冷却塔出水温度 | output |
| 2a6a59ff_6a08_4cab_9466_ffd7784b7af2 | 8#冷却塔出水温度 | output |
| a616e7a5_256e_474b_845a_1d2a90501361 | 1#冷冻流量 | output |
| d4d52740_8708_4948_aeed_b31db72a55b2 | 2#冷冻流量 | output |
| 2cc6d2c9_4bd2_402d_86db_6312cd3e2ec9 | 1#冷冻泵流量 | output |
| 20f5539c_76b4_4b67_b3f4_778ee0249861 | 2#冷冻泵流量 | output |
| 083fcd86_7d54_4eab_b230_361c468db6f2 | 3#冷冻泵流量 | output |
| e99ad1be_a413_4c14_accb_abcf0b113049 | 4#冷冻泵流量 | output |
| d068e9c2_cc13_4429_8f00_74b9eb2e9efe | 1#冷却流量 | output |
| f33d9a62_38da_4eb6_b3ee_80860711640b | 2#冷却流量 | output |
| 62425c39_ad95_41ca_95ac_ccf03323279a | 1#冷却泵流量 | output |
| 54746436_93d5_4296_bf91_0943ffa7e60b | 2#冷却泵流量 | output |
| 3dad770e_54f8_4625_a3d4_ab309cdec95a | 3#冷却泵流量 | output |
| 79cd63eb_7d18_4dc6_b6ec_1aee7db83ef6 | 4#冷却泵流量 | output |
| nodeZNV.00001006000000000086.0116145001 | 109空调配电室/1AK2柜-1#冷水主机.正向有功电能 | output |
| nodeZNV.00001006000000001536.0116145001 | 109空调配电室/4AK4柜-2#冷水机组L-2电表.正向有功电能 | output |
| nodeZNV.00001006000000000169.0116145001 | 109空调配电室/2AK4柜-3#冷水主机.正向有功电能 | output |
| nodeZNV.00001006000000000080.0116145001 | 109空调配电室/3AK2柜-4#冷水主机主用.正向有功电能 | output |
| nodeZNV.00001006000000000095.0116145001 | 109空调配电室/1AK2柜-1#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000001534.0116145001 | 109空调配电室/4AK4柜-2#冷冻泵电表.正向有功电能 | output |
| nodeZNV.00001006000000000174.0116145001 | 109空调配电室/2AK4柜-3#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000000078.0116145001 | 109空调配电室/3AK2柜-4#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000000090.0116145001 | 109空调配电室/1AK2柜-1#冷却泵.正向有功电能 | output |
| nodeZNV.00001006000000001535.0116145001 | 109空调配电室/4AK4柜-2#冷却泵电表.正向有功电能 | output |
| nodeZNV.00001006000000000175.0116145001 | 109空调配电室/2AK4柜-3#冷却泵.正向有功电能 | output |
| nodeZNV.00001006000000000079.0116145001 | 109空调配电室/3AK2柜-4#冷却泵.正向有功电能 | output |
| efbff8e2_dcfb_494e_aead_a2d46cd5fe77 | 1#冷冻泵电压 | output |
| 6b24aa30_667c_46ce_92f8_d624cc6688b4 | 1#冷冻泵电流 | output |
| 606852c3_6961_49c8_a654_37a905fce06e | 1#冷却塔电压 | output |
| cc1045c8_6e36_48e0_8202_6a848a442418 | 1#冷却塔电流 | output |
| 5e3afa6c_6003_4529_b6e6_2c4252c729c8 | 2#冷却塔电压 | output |
| 0f160bd4_6d42_43a9_be08_56a91673dcf7 | 2#冷却塔电流 | output |
| 8ff98ce7_fe5a_4d75_a1e1_aa17644a49c3 | 1#压缩机A相电流 | output |
| 0913a4fe_7e4d_4238_b156_6ca74a383173 | 1#压缩机B相电流 | output |
| d5833526_3740_42b6_b04e_49abbf412a16 | 1#压缩机C相电流 | output |
| c30840bd_072c_46a5_a7de_6d6b7db7596f | 2#冷冻泵电压 | output |
| 10fa55d9_60f8_4491_a64d_e4c3c844d5ec | 2#冷冻泵电流 | output |
| e3d11f8d_9615_4808_87e9_9de4661db34c | 2#冷却泵电压 | output |
| e7e075f3_8d85_4469_b0af_fed6aeb1c4f7 | 2#冷却泵电流 | output |
| 0d2b7ca4_2511_4468_8721_b162f1855037 | 7#冷却塔电压 | output |
| 23512f23_00fe_474b_8928_223731949a2c | 7#冷却塔电流 | output |
| 058d58b7_bc8a_474f_9e82_5dd563ce574f | 8#冷却塔电压 | output |
| 758c41c0_35da_4953_b1f0_93f89ddbe783 | 8#冷却塔电流 | output |
| 0ca13caa_052a_4abf_80bf_c8c55e2bec52 | 1#压缩机电流百分比 | output |
| addba2cc_98aa_4794_9a09_f5e746d6e4fd | 2#压缩机电流百分比 | output |
| 8f9a84ff_71be_4180_b237_22cdd43abc6f | 2#压缩机A相电流 | output |
| bafd3567_9b9c_43dc_9057_b531e733c53d | 2#压缩机B相电流 | output |
| 0847f871_f1d0_4d62_8288_0c47ccf8477b | 2#压缩机C相电流 | output |
| 0f0072ff_d384_4554_b009_69e75bdbddf7 | 3#冷冻泵电压 | output |
| 3b7c16c1_7a98_454a_9a6a_78f410b9fc12 | 3#冷冻泵电流 | output |
| 49f38bdf_e016_4c04_9b80_3ffcc2332ed3 | 3#冷却泵电压 | output |
| 5aed8639_7773_4a0e_b4e7_ee149b62b901 | 3#冷却泵电流 | output |
| 9b93eed9_4eca_4a8b_91c4_ef56d0cb4333 | 3#冷却塔电压 | output |
| 0d04a4a9_edd3_40a9_80ce_885e52787623 | 3#冷却塔电流 | output |
| 97e573de_bbb1_405d_8fcf_6062036f8211 | 4#冷却塔电压 | output |
| 72d4ac6c_e592_443f_bea3_2093a562a623 | 4#冷却塔电流 | output |
| c6731afa_c189_4f29_866d_8b1a6905338a | 3#压缩机电流百分比 | output |
| 82a9e94b_16f3_4906_b14e_389ac3b9acdf | 3#压缩机A相电流 | output |
| fb636b66_f78f_4296_a844_cb077fcef13a | 3#压缩机B相电流 | output |
| b5d1318c_12c3_43d1_b568_669fdcbe558b | 3#压缩机C相电流 | output |
| 9b5bdb29_b693_40fb_837c_7b0e14b780ae | 4#冷冻泵电压 | output |
| 7e91bf2d_dc90_4286_9c8d_dae1dcdb1736 | 4#冷冻泵电流 | output |
| c3fd84e4_9b9b_45ac_a993_d93203553975 | 4#冷却泵电压 | output |
| 11c7e90b_1303_4029_a5f8_a8bf5c640780 | 4#冷却泵电流 | output |
| 5593c817_3be8_4373_8054_88495d7a7057 | 5#冷却塔电压 | output |
| 13e85966_e1b6_43f9_848b_66ac7b6b8046 | 5#冷却塔电流 | output |
| 4d78f278_c743_4d51_820c_bc6823a58a76 | 6#冷却塔电压 | output |
| c953a3b1_95bc_455e_9b27_ca105e8dff63 | 6#冷却塔电流 | output |
| e5b65ddd_0bed_4436_aba2_d5c18f141850 | 4#压缩机电流百分比 | output |
| 3e088f0f_0d68_4379_b76d_2671d48ef2b4 | 4#压缩机A相电流 | output |
| 91bdd4d8_c9ca_44d7_b126_e91b4b798977 | 4#压缩机B相电流 | output |
| 78b88569_0bfb_4d86_9deb_09c6c30fab66 | 4#压缩机C相电流 | output |
| 9aa15548_c1ad_4ae8_9122_4f9ba250361e | 1#冷却泵电压 | output |
| 616cb0c3_5be5_4a8d_955a_883d799a671d | 1#冷却泵电流 | output |

### 输入：inputs
| uid | name | category |
| --- | --- | --- |
| f20f7350_ddd6_45e3_b10a_a63f01a6cd4b | 冷冻总管供水平均温度 | input |
| a13176bb_3bb7_4adc_8eb7_66dfa911f43c | 冷冻侧泵组运行数量 | input |
| 58a01135_6239_40aa_a2bb_e5dd214e6e1a | 1#冷冻泵运行状态 | input |
| 60d8edcb_16fb_449e_bfce_c3638d6cf73d | 1#冷冻泵变频反馈 | input |
| f89cad89_7c54_4cd2_b698_8bc02a31b1a7 | 1#冷却泵运行状态 | input |
| b879c1f5_4aa9_4c0c_99b1_a5f78be1279b | 1#冷却泵变频反馈 | input |
| a1943b1f_7236_4997_9721_aa3f67f66127 | 1#冷却塔运行状态 | input |
| df552485_196f_4436_b076_74708bd4e73c | 1#冷却塔变频反馈 | input |
| 145cbc6c_ae10_414e_a5e9_fdd96d45138f | 2#冷却塔运行状态 | input |
| bec138b8_d749_47a2_9914_d271688e5947 | 2#冷却塔变频反馈 | input |
| 8e26d9a1_8c6f_4966_86df_078f8360f7c5 | V16阀门开反馈 | input |
| 1d085c1b_142d_4fb5_b6a1_8d878239db06 | V20阀门开反馈 | input |
| b80c7278_cb6c_40c2_8984_b002b992c1e4 | V21阀门开反馈 | input |
| 30699c72_4993_4487_be2d_f80a29168da1 | V22阀门开反馈 | input |
| 87ec99a8_3af2_497d_b877_1b01504696b9 | V23阀门开反馈 | input |
| b5b56961_868c_432f_b09a_986a7208c793 | V24阀门开反馈 | input |
| 3a595b52_ae59_424a_82f4_3436842db552 | 1#冷机运行状态 | input |
| 566185d4_6cac_4dcc_a52a_0b3bece9d920 | 1#冷机冷冻出水温度 | input |
| 61db6ac0_eeef_44d5_9f86_a7a2c07c74be | 1#冷机冷却进水温度 | input |
| 2976cfd2_6b50_4bf7_abfc_4d9806c81409 | 1#冷机冷冻水流开关 | input |
| c035e2a7_def9_430d_8e4c_9795a9765d8c | 1#冷机冷却水流开关 | input |
| 661ec640_59f7_4f8e_92f7_90d57b3abe7a | 1#冷机压缩机冷凝压力 | input |
| ddfc7ccd_dfa4_4258_8737_bb388acda4e8 | 1#冷机压缩机冷凝温度 | input |
| 83b2f5e2_27bd_4518_a34b_adc9bb6b57c1 | 1#冷机压缩机蒸发压力 | input |
| 30884cf5_21b4_4660_8a6e_8d36c8de6c0c | 1#冷机压缩机蒸发温度 | input |
| d80c57d4_9a7b_486d_9994_af3b64ddcc20 | 1#压缩机排气温度 | input |
| 6c7e3bf8_235e_4aad_a1d7_31a50eb9cce7 | 1#压缩机吸气温度 | input |
| 033d216c_087a_49b1_a431_c0544e12f815 | 1#压缩机供油温度 | input |
| 22c0a671_9a64_4bb2_9c41_025276ef1854 | 1#压缩机供油压力 | input |
| ca2d82a6_8c13_41b5_a3ab_25dc8ff8ce41 | 1#压缩机油箱温度 | input |
| 9560a394_b12c_4e3a_9562_44f5e829977a | 1#压缩机油箱压力 | input |
| 9f6f28dd_70b4_4c7c_964e_c1ca7990ca48 | 1#压缩机运行时间 | input |
| ded19ee4_432c_4580_8463_693e7f4103d7 | 1#压缩机启动次数 | input |
| 18df604b_1891_47be_8e76_05a8f0cdac0d | 1#压缩机导叶开度 | input |
| 69754e31_94b6_43d4_9186_4e5ddf477f9f | 2#冷冻泵运行状态 | input |
| 30b063e7_c72d_4678_bfcb_5f4c95f21818 | 2#冷冻泵变频反馈 | input |
| 2f7c59da_0a9d_4616_8772_3f79a79edb29 | 2#冷却泵运行状态 | input |
| 696a1edc_d719_44cb_96dd_f121bc2b5e95 | 2#冷却泵变频反馈 | input |
| c4cc5563_4894_43ff_be68_a0dcfd10c539 | 7#冷却塔运行状态 | input |
| 6bd2f5ca_85a4_4e24_b6f1_087a3124355b | 7#冷却塔变频反馈 | input |
| 59b2bb9a_09a1_429c_ac5d_86a54a9996cd | 8#冷却塔运行状态 | input |
| 1ee5af99_9870_4eaf_ae35_247dd98b7619 | 8#冷却塔变频反馈 | input |
| 399ba9b0_76e3_47b8_b4fe_8b501fb800f3 | V15阀门开反馈 | input |
| a8126950_147a_411a_954d_9047a94d5192 | V19阀门开反馈 | input |
| 1e50eba8_942a_4873_9d79_dcb61b43a854 | V33阀门开反馈 | input |
| 6d21f8aa_bfef_42a3_bb7c_7c1547481970 | V34阀门开反馈 | input |
| 357b9ca1_0232_47bd_9f01_e40ba35ca315 | V35阀门开反馈 | input |
| 4e34021e_146b_4e74_9caa_003e01c912bd | V36阀门开反馈 | input |
| f6f72a01_6520_4139_9a80_4ad143cf7754 | 2#冷机运行状态 | input |
| 650186e2_c232_4ad0_a13c_7c572ea1f883 | 2#冷机冷冻出水温度 | input |
| 96767a02_149a_4d99_9e7f_118a155bacee | 2#冷机冷却进水温度 | input |
| fc863933_4222_4aa8_a536_028a7edc187d | 2#冷机冷冻水流开关 | input |
| 0f7de855_f0f8_4df1_b3d4_4ec2f08e9bb2 | 2#冷机冷却水流开关 | input |
| 2f25b14e_1a57_4bd4_bfdf_aaf313a659f2 | 2#冷机压缩机冷凝压力 | input |
| de2ee3a3_59bc_455f_bd44_59c3d395641a | 2#冷机压缩机冷凝温度 | input |
| 21f97585_e749_4ab9_977a_df025218be5c | 2#冷机压缩机蒸发压力 | input |
| 83300e4d_b532_40c7_b191_380b9e215cbb | 2#冷机压缩机蒸发温度 | input |
| a29ebf0f_5464_4f37_b5cb_92194be3fd1b | 2#压缩机排气温度 | input |
| 9aaabaa4_138f_4aff_b0c7_9d4db32f3981 | 2#压缩机吸气温度 | input |
| 951925ea_b093_49ae_b9cf_d769e975d39a | 2#压缩机供油温度 | input |
| 4b0e10bf_9531_4066_adbf_ce7a5592195c | 2#压缩机供油压力 | input |
| dc090ac8_40b1_4200_b1c5_ef3624fb7971 | 2#压缩机油箱温度 | input |
| 8fb77b0f_de8e_4c12_9165_f228909b95d9 | 2#压缩机油箱压力 | input |
| c9408206_ac3d_497c_bd14_40880f4a0835 | 2#压缩机运行时间 | input |
| 4b0aad38_85eb_432c_af69_4dc0bf0dbee5 | 2#压缩机启动次数 | input |
| 61d52025_2006_4bfe_92af_61bbc1ad9b11 | 2#压缩机导叶开度 | input |
| 5089e1e2_28f7_4b51_b926_58f53a2b5f21 | 3#冷冻泵运行状态 | input |
| a8cc0e6a_0454_4896_bc51_535c060b5ed3 | 3#冷冻泵变频反馈 | input |
| 3827ba36_feea_45e2_ba6e_9ca4372195b3 | 3#冷却泵运行状态 | input |
| e8576c13_913e_4a8e_a726_18ed0a3bca70 | 3#冷却泵变频反馈 | input |
| 9299aa1f_5e9e_4fcb_b541_840d9dd5e918 | 3#冷却塔运行状态 | input |
| 8d7d5f68_fe38_4567_89e7_47698604ebf0 | 3#冷却塔变频反馈 | input |
| e5d315ff_39b0_4472_bdcb_5ecdb78eb5ee | 4#冷却塔运行状态 | input |
| 47d97a4e_a6d8_45b9_a054_a9cbe052b596 | 4#冷却塔变频反馈 | input |
| 5d25ea2e_8fb9_49ad_bdb7_c375f5a81365 | V14阀门开反馈 | input |
| 75d5916e_0731_47fe_9809_808aa55083bd | V18阀门开反馈 | input |
| df77248d_8de9_4dfa_8028_edf3a8ca8faa | V25阀门开反馈 | input |
| e1fd6894_d83b_484f_a1af_13a1753d170c | V26阀门开反馈 | input |
| 16dab63c_23a4_4731_8960_d922d526bae3 | V27阀门开反馈 | input |
| 517f633d_670e_425b_a4f2_b4a1c7771e30 | V28阀门开反馈 | input |
| d648d72d_e8a3_4260_b309_50496c5e098d | 3#冷机运行状态 | input |
| 8ff4a8f3_0a2f_486e_b758_2219f1cfbb23 | 3#冷机冷冻出水温度 | input |
| 263ca4a7_70ae_4e17_8d22_58985fca090a | 3#冷机冷却进水温度 | input |
| 663dd565_fe66_4139_a6af_6b594aab537b | 3#冷机冷冻水流开关 | input |
| 6a98e949_6822_4147_aeeb_4277e3109d69 | 3#冷机冷却水流开关 | input |
| e8b005ca_cfaa_464f_b915_70846aca2dc2 | 3#冷机压缩机冷凝压力 | input |
| 52c5c44a_12ff_4df5_b9e4_13659e2ba17c | 3#冷机压缩机冷凝温度 | input |
| 5f2edc83_21e9_452f_a34e_a5c15e85aae9 | 3#冷机压缩机蒸发压力 | input |
| 5554a220_5845_4a2f_ad4c_f8445d909ad8 | 3#冷机压缩机蒸发温度 | input |
| 87f632f9_ee0e_41e9_8975_378693348259 | 3#压缩机排气温度 | input |
| 91c7920c_ce5b_464a_9bd8_e463d763a811 | 3#压缩机吸气温度 | input |
| 5d33aa25_11cf_46c3_a03c_c1e9a1a86480 | 3#压缩机供油温度 | input |
| 7cf0b0c9_6879_4f2c_9ca4_439ffa62087e | 3#压缩机供油压力 | input |
| 59b0e9db_7c64_4a73_b2ba_e3fcd36ce4ab | 3#压缩机油箱温度 | input |
| e242f52c_2433_4b93_ae11_8e583acf8260 | 3#压缩机油箱压力 | input |
| ff57a76d_3397_4b93_8fc0_fbb8ff86c0fa | 3#压缩机运行时间 | input |
| e5f579e6_2ff3_4d7e_a952_eb0bf401e338 | 3#压缩机启动次数 | input |
| 5e881b26_92a5_4c14_aba8_dab0367b39c4 | 3#压缩机导叶开度 | input |
| 3c36faf1_ab54_4189_93f8_47931d0fdcfa | 4#冷冻泵运行状态 | input |
| 8556e1c4_a5f2_442a_a427_cc5e5c5ac174 | 4#冷冻泵变频反馈 | input |
| 3ccf760d_79ef_461f_943b_4332f244e52a | 4#冷却泵运行状态 | input |
| 048a2967_b98c_4cd7_a792_fa596fd26ce0 | 4#冷却泵变频反馈 | input |
| 801c1f70_8bdf_44c6_ac8c_3df87849ee86 | 5#冷却塔运行状态 | input |
| 96400def_89d2_4691_bd06_3d4255f0fe70 | 5#冷却塔变频反馈 | input |
| adafe57a_392f_497d_bb81_c04814c4a27c | 6#冷却塔运行状态 | input |
| 2b99abf9_3fd1_4e25_8094_c63c842520a7 | 6#冷却塔变频反馈 | input |
| 273b6bfc_fd50_4f9d_9048_678ba9da7fef | V13阀门开反馈 | input |
| f4b5cb5d_333e_41d9_bd14_d453a7a9894c | V17阀门开反馈 | input |
| db0edab2_5819_4183_a9be_973a8720a094 | V29阀门开反馈 | input |
| 08de0a56_7e56_4afb_aa41_c0224f6ab33f | V30阀门开反馈 | input |
| 19fbd577_c90e_45b2_a183_769609f23051 | V31阀门开反馈 | input |
| 0aa525c6_4172_4286_8a62_2997be27bdc8 | V32阀门开反馈 | input |
| 2f369795_a3ae_44ab_b19c_9eaebfd1a5f4 | 4#冷机运行状态 | input |
| abb8c9a3_d5de_437a_9fdc_8219bc851c73 | 4#冷机冷冻出水温度 | input |
| db8f1027_7dd8_4c30_8255_ccb5d86edbbb | 4#冷机冷却进水温度 | input |
| ff4bb6aa_86fe_41f7_bd68_8485cbbd14db | 4#冷机冷冻水流开关 | input |
| c25b59d6_4384_4de6_b844_a024b8156d4e | 4#冷机冷却水流开关 | input |
| 060c06d3_80bf_4b11_8f77_5dc6607382d3 | 4#冷机压缩机冷凝压力 | input |
| eb8ebf3e_7532_4f46_b219_bce9e5788a59 | 4#冷机压缩机冷凝温度 | input |
| 65373c2d_ff43_4bbd_8224_6d699002f301 | 4#冷机压缩机蒸发压力 | input |
| 5ee286eb_790f_4215_a985_cb5371c30595 | 4#冷机压缩机蒸发温度 | input |
| 9c889d9f_1c9b_4dad_9e9f_fb2d5c1724bb | 4#压缩机排气温度 | input |
| 1e432ca9_c346_4949_b992_aa9876f472c5 | 4#压缩机吸气温度 | input |
| 714b8c90_ac24_48ef_b3b0_2b64b9f4e85c | 4#压缩机供油温度 | input |
| 84a266ff_3e80_4eb7_a5a6_6cb0f7699f7e | 4#压缩机供油压力 | input |
| d3351f21_de57_44c0_8d3b_5c4fa02e4a15 | 4#压缩机油箱温度 | input |
| e1d9ed98_07b4_45b1_befe_12febfe97c69 | 4#压缩机油箱压力 | input |
| 75d25dc4_c47d_4e45_b223_3e6f306985fa | 4#压缩机运行时间 | input |
| f729642f_7d6d_4b24_866d_4374295014d8 | 4#压缩机启动次数 | input |
| d71ae6ce_bc1c_4105_907d_4e60cb470b9a | 4#压缩机导叶开度 | input |
| b49cbca4_9c92_4465_8d74_aedb26caaf7d | 冷冻供水温度1 | input |
| b51902d0_5e16_46d8_bf49_0f16b1a69cf9 | 冷冻供水温度2 | input |
| be17c8f1_d1a9_4456_a9f3_20ccb2563c0e | 冷却供水温度1 | input |
| fe1825a2_99fa_47f4_b5bf_879fffb8c713 | 冷却供水温度2 | input |
| d2149f6a_765e_4f2d_8694_ad94dc8b2afa | 冷却塔1液位 | input |
| 4ab18378_579f_4578_a3c4_62547bad370e | 冷却塔2液位 | input |
| 35e76193_bc42_4445_902c_88c0715f24c1 | 冷却塔3液位 | input |
| b3e7f3d0_2cda_4a60_b91a_192fa5948d9b | 冷却塔4液位 | input |
| bfd832b1_75ca_48d3_8adc_a813fdec889d | 冷冻供水压力1 | input |
| db5fa386_e55e_44d9_8b3e_2a7b4b64695e | 冷冻供水压力2 | input |
| 21e832f2_c61b_4583_b813_b6c888166290 | 冷却供水压力1 | input |
| f74ffff3_67d1_4568_ab49_01c06e86e216 | 冷却供水压力2 | input |
| 49d2c581_74f9_4d38_b1c1_b07960bc6962 | 冷冻回水压力1 | input |
| 1b3bd1f5_2e73_4b6d_afc1_11bfae751321 | 冷冻回水压力2 | input |
| 3efac490_d89f_4ee9_bddb_53625615642f | 冷却回水温度1 | input |
| ea89ebf3_d9d3_4794_89ad_3cb069f1e819 | 冷却回水温度2 | input |
| c10dcdd7_e5c1_4cc2_bc86_f8980b5c460b | 冷冻水总管压差旁通阀开度1 | input |
| 63eb976b_d774_4631_8780_c85dbbd7e0c1 | 冷冻水总管压差旁通阀开度2 | input |
| 0e61a321_0066_4b4a_b5d2_1cc98cf828c5 | 蓄冷水池温度 | input |
| b5bce5c0_0ac3_40bb_b18e_2ca7f2287fc6 | 蓄冷水池低液位 | input |
| c9003757_01aa_4ad5_a993_b23f7e2baf89 | 冷冻水补水箱低液位 | input |
| 3b7a98f7_105e_4b12_a2b2_afa6d8f37cdb | 冷却水补水箱低液位 | input |
| 51e57b9a_5efa_4a26_af3c_738570328be8 | 软化水箱低液位 | input |
| 692dfa13_c931_41fb_8516_28d877a12cd0 | 1#冷冻补水补水泵运行状态 | input |
| c65d3709_5673_4fc0_b764_75289ff72218 | 2#冷冻补水补水泵运行状态 | input |
| acd7036f_a666_4e64_bbe6_1d39ae115575 | 1#冷却补水补水泵运行状态 | input |
| 1ddb4f7e_e7c2_4368_85f7_9ef91c5546d2 | 2#冷却补水补水泵运行状态 | input |
| dacf3aba_2fe4_4d53_8453_d410ddf13410 | 3#冷却补水补水泵运行状态 | input |
| ecebff91_3df3_4faa_b095_582687f74890 | 1#蓄冷泵运行状态 | input |
| 64b7634e_e6b5_47db_bcd2_5d651025e1e0 | 2#蓄冷泵运行状态 | input |
| ba23f42c_2ed7_4372_8704_2d64cd872273 | 1#放冷泵运行状态 | input |
| 0aa02cf0_8987_447c_909a_6da866756baa | 2#放冷泵运行状态 | input |
| 00ef6889_e752_4c8c_9734_49733894da18 | 蓄冷水池温度1 | input |
| e20aff36_dc87_41d0_a4d9_734a40b078c1 | 蓄冷水池温度2 | input |
| 6b564f71_d565_4ce6_bde9_d98285bd08c3 | 蓄冷水池温度3 | input |
| 29a1358a_0b9b_403d_8026_d2238510e1fd | 蓄冷水池温度4 | input |
| f18f8a23_cc12_4dcf_8f55_df2e70f6719f | 蓄冷水池温度5 | input |
| 0a0d4745_8da1_4108_9ff2_c8c158d4e572 | 蓄冷水池温度6 | input |
| fe9c84ca_70b7_41e5_b665_ac3a7c1b1618 | 蓄冷水池温度7 | input |
| 4d1b16cc_17e6_4114_be63_33070a941d21 | 蓄冷水池温度8 | input |
| 339e6b10_49a1_4072_9a69_cab7f1f086bc | 蓄冷水池温度9 | input |
| 9d603c44_a403_4adf_9b15_5be2a799cfb7 | 蓄冷水池温度10 | input |
| fec9da0b_e91c_4b9b_87d3_5af56d47e4b4 | 蓄冷水池温度11 | input |
| 1a622fb4_09a8_4835_8d83_289b187b921b | 蓄冷水池温度12 | input |
| 648184da_d7b3_4475_be37_ba007f171d93 | 蓄冷水池温度13 | input |
| a0839617_311b_45a4_9bf8_58d78dc30c30 | 蓄冷水池温度14 | input |
| ee2160eb_5847_4d86_b176_aeb50d860817 | 蓄冷水池温度15 | input |
| d1c5e7fd_9ef9_49ec_95fd_511376ab2d6c | 蓄冷水池温度16 | input |
| 20d2046c_a667_43ba_bdcf_bd3be92c4c1f | 蓄冷水池温度17 | input |
| 59ab0655_2060_4e7b_a1cb_58cf1081184e | 蓄冷水池温度18 | input |
| 6d305d17_c03e_402a_9b1d_34e30de99de7 | 蓄冷水池温度19 | input |
| 6630c2f3_89ab_4bdc_a872_495d71e0ab8e | 蓄冷水池温度20 | input |
| 1b6648d8_de60_4c06_ad77_8e95f99b35ce | 蓄冷水池温度21 | input |
| c34c8556_9701_4bd0_83e6_81a9a2528626 | 蓄冷水池温度22 | input |
| 5c31c03b_ebab_466a_8cf8_597b6abee54e | 蓄冷水池温度23 | input |
| 6e36ca85_e895_47fb_86a8_4d57a85c1db7 | 蓄冷水池温度24 | input |
| fb6d9bbb_0239_4cbf_b43f_e2b9fbcd1dc1 | 蓄冷水池温度25 | input |
| 569a751c_724f_44c9_9f8d_19822f347bba | 蓄冷水池温度26 | input |
| bd8c9c88_11dc_41c5_b2c4_3c0a346ec73d | 蓄冷水池液位 | input |
| 48dec2b7_15d8_46bd_9ca5_425d08eb9e3e | 放冷泵变频温度设定 | input |
| 2b97ca6d_552f_4969_b788_341d9e2b0b01 | 1#冷却塔变频设定 | input |
| e630880e_c26c_42ce_9f65_db9c8c004d6f | 2#冷却塔变频设定 | input |
| 647c0ba7_2e10_4ea5_b91e_7134c3c58549 | 3#冷却塔变频设定 | input |
| d0ff09d3_99e1_4a2e_8f54_3518a9fad009 | 4#冷却塔变频设定 | input |
| 115d9f10_2da6_4701_81fd_16a5158c53cb | 5#冷却塔变频设定 | input |
| eaf016d6_67f4_442b_bc3f_39e45888afb9 | 6#冷却塔变频设定 | input |
| 4e81df63_5381_4d50_b649_e9e2a3512a57 | 7#冷却塔变频设定 | input |
| 6b2b6bfa_4029_49fc_825f_61123d89ba52 | 8#冷却塔变频设定 | input |
| 312687b0_4b8d_4d62_a89a_21398665ca49 | 1#冷冻泵变频设定 | input |
| ba601eb9_f737_43ce_97dc_f48de3808239 | 2#冷冻泵变频设定 | input |
| b1b5bbed_c938_4a1c_a3e1_21b13eea6bbf | 3#冷冻泵变频设定 | input |
| 717c5095_5c42_4177_844f_d635ecfe5b60 | 4#冷冻泵变频设定 | input |
| 68309b77_e1c4_4a43_85e7_d6b50c3d9bd4 | 1#冷却泵变频设定 | input |
| 2fa838ba_c3d1_47c2_a67e_da00439d7550 | 2#冷却泵变频设定 | input |
| 67c01069_ea42_4b83_bb45_69ecc8939487 | 3#冷却泵变频设定 | input |
| c6d0599c_83d4_41f5_a9a3_78987a6adb9f | 4#冷却泵变频设定 | input |
| a489cb8c_87b1_4d7f_8fb9_12c624f80e7c | 放冷流量 | input |
| d05acf6e_9d5d_4017_a3b0_07a68e26945a | 室外湿度 | input |
| 638dfc04_812d_4d72_a474_065d535846c9 | 室外温度 | input |
| 0be2c792_a4cc_4681_9b43_96e147d856ad | 1#放冷泵变频反馈 | input |
| 1e480205_197e_4b6a_8e4a_15e04bf2cb3a | 2#放冷泵变频反馈 | input |
| 39d9aaef_5d8b_426d_b104_8a41d056b8eb | 1#蓄冷泵变频反馈 | input |
| 6a5da06b_4626_4023_814a_7f88bdf47e13 | 2#蓄冷泵变频反馈 | input |
| dd978620_c2cc_4831_a77f_d5f5b2206ee8 | 1#放冷泵变频设定 | input |
| 70de1bfc_b4b6_4814_80fd_044b40c86da1 | 2#放冷泵变频设定 | input |
| e6848a16_7b91_4e50_9f82_ae57ece8f700 | 1#蓄冷泵变频设定 | input |
| 96071936_4def_471f_b92f_5f4042a19702 | 2#蓄冷泵变频设定 | input |

### 输入：输出状态（state_{uid}，用于自回归）
| base_uid | name | category |
| --- | --- | --- |
| 26aa984f_ddc1_4c33_9c96_b3313aad2a72 | 冷冻总管回水平均温度 | output |
| 4398dbf6_8f98_4222_9f58_4e91feab323d | 蓄冷水池平均温度 | output |
| b1858cac_4abf_4789_8a62_6c1aec8615c6 | 1#冷机冷冻进水温度 | output |
| 8f3102af_f9e3_4a68_b191_bc1a995af0c4 | 1#冷机冷却出水温度 | output |
| 7479ada1_b9b3_41b4_a3fa_05e3d4969d04 | 2#冷机冷冻进水温度 | output |
| 0cce079d_2e85_4711_b973_e9e3b9bc30a3 | 2#冷机冷却出水温度 | output |
| d8f07bad_c577_4b09_96f9_5a989212ddfb | 3#冷机冷冻进水温度 | output |
| 0a9f2a34_183d_4434_b2b4_dc581d25e29a | 3#冷机冷却出水温度 | output |
| 0d4d1f7d_d7e0_46ff_9779_b92f59b1ab04 | 4#冷机冷冻进水温度 | output |
| 3d88232c_0a10_452c_aa67_c8d0737a93a7 | 4#冷机冷却出水温度 | output |
| 7c70b29c_173e_4b3a_9cb7_e49af1206593 | 冷冻回水温度1 | output |
| aa95fde4_879a_468d_9a2a_cbd63121cb68 | 冷冻回水温度2 | output |
| 0a85728b_efa0_42e5_aa27_81c30fb45786 | 1#冷却塔出水温度 | output |
| fa492a03_c5df_42d4_96df_7eef051bb972 | 2#冷却塔出水温度 | output |
| 73c216fa_7de6_4b7a_827b_2b3caaa7ab94 | 3#冷却塔出水温度 | output |
| d712284a_e38f_4433_b507_ca48b5977b42 | 4#冷却塔出水温度 | output |
| 46902447_9fe5_45bc_8f59_e17471cbead8 | 5#冷却塔出水温度 | output |
| 1b1de943_5762_4279_b7dc_7867c706718f | 6#冷却塔出水温度 | output |
| dd80b34a_e30e_4076_9182_ca306c58d890 | 7#冷却塔出水温度 | output |
| 2a6a59ff_6a08_4cab_9466_ffd7784b7af2 | 8#冷却塔出水温度 | output |
| a616e7a5_256e_474b_845a_1d2a90501361 | 1#冷冻流量 | output |
| d4d52740_8708_4948_aeed_b31db72a55b2 | 2#冷冻流量 | output |
| 2cc6d2c9_4bd2_402d_86db_6312cd3e2ec9 | 1#冷冻泵流量 | output |
| 20f5539c_76b4_4b67_b3f4_778ee0249861 | 2#冷冻泵流量 | output |
| 083fcd86_7d54_4eab_b230_361c468db6f2 | 3#冷冻泵流量 | output |
| e99ad1be_a413_4c14_accb_abcf0b113049 | 4#冷冻泵流量 | output |
| d068e9c2_cc13_4429_8f00_74b9eb2e9efe | 1#冷却流量 | output |
| f33d9a62_38da_4eb6_b3ee_80860711640b | 2#冷却流量 | output |
| 62425c39_ad95_41ca_95ac_ccf03323279a | 1#冷却泵流量 | output |
| 54746436_93d5_4296_bf91_0943ffa7e60b | 2#冷却泵流量 | output |
| 3dad770e_54f8_4625_a3d4_ab309cdec95a | 3#冷却泵流量 | output |
| 79cd63eb_7d18_4dc6_b6ec_1aee7db83ef6 | 4#冷却泵流量 | output |
| nodeZNV.00001006000000000086.0116145001 | 109空调配电室/1AK2柜-1#冷水主机.正向有功电能 | output |
| nodeZNV.00001006000000001536.0116145001 | 109空调配电室/4AK4柜-2#冷水机组L-2电表.正向有功电能 | output |
| nodeZNV.00001006000000000169.0116145001 | 109空调配电室/2AK4柜-3#冷水主机.正向有功电能 | output |
| nodeZNV.00001006000000000080.0116145001 | 109空调配电室/3AK2柜-4#冷水主机主用.正向有功电能 | output |
| nodeZNV.00001006000000000095.0116145001 | 109空调配电室/1AK2柜-1#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000001534.0116145001 | 109空调配电室/4AK4柜-2#冷冻泵电表.正向有功电能 | output |
| nodeZNV.00001006000000000174.0116145001 | 109空调配电室/2AK4柜-3#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000000078.0116145001 | 109空调配电室/3AK2柜-4#冷冻泵.正向有功电能 | output |
| nodeZNV.00001006000000000090.0116145001 | 109空调配电室/1AK2柜-1#冷却泵.正向有功电能 | output |
| nodeZNV.00001006000000001535.0116145001 | 109空调配电室/4AK4柜-2#冷却泵电表.正向有功电能 | output |
| nodeZNV.00001006000000000175.0116145001 | 109空调配电室/2AK4柜-3#冷却泵.正向有功电能 | output |
| nodeZNV.00001006000000000079.0116145001 | 109空调配电室/3AK2柜-4#冷却泵.正向有功电能 | output |
| efbff8e2_dcfb_494e_aead_a2d46cd5fe77 | 1#冷冻泵电压 | output |
| 6b24aa30_667c_46ce_92f8_d624cc6688b4 | 1#冷冻泵电流 | output |
| 606852c3_6961_49c8_a654_37a905fce06e | 1#冷却塔电压 | output |
| cc1045c8_6e36_48e0_8202_6a848a442418 | 1#冷却塔电流 | output |
| 5e3afa6c_6003_4529_b6e6_2c4252c729c8 | 2#冷却塔电压 | output |
| 0f160bd4_6d42_43a9_be08_56a91673dcf7 | 2#冷却塔电流 | output |
| 8ff98ce7_fe5a_4d75_a1e1_aa17644a49c3 | 1#压缩机A相电流 | output |
| 0913a4fe_7e4d_4238_b156_6ca74a383173 | 1#压缩机B相电流 | output |
| d5833526_3740_42b6_b04e_49abbf412a16 | 1#压缩机C相电流 | output |
| c30840bd_072c_46a5_a7de_6d6b7db7596f | 2#冷冻泵电压 | output |
| 10fa55d9_60f8_4491_a64d_e4c3c844d5ec | 2#冷冻泵电流 | output |
| e3d11f8d_9615_4808_87e9_9de4661db34c | 2#冷却泵电压 | output |
| e7e075f3_8d85_4469_b0af_fed6aeb1c4f7 | 2#冷却泵电流 | output |
| 0d2b7ca4_2511_4468_8721_b162f1855037 | 7#冷却塔电压 | output |
| 23512f23_00fe_474b_8928_223731949a2c | 7#冷却塔电流 | output |
| 058d58b7_bc8a_474f_9e82_5dd563ce574f | 8#冷却塔电压 | output |
| 758c41c0_35da_4953_b1f0_93f89ddbe783 | 8#冷却塔电流 | output |
| 0ca13caa_052a_4abf_80bf_c8c55e2bec52 | 1#压缩机电流百分比 | output |
| addba2cc_98aa_4794_9a09_f5e746d6e4fd | 2#压缩机电流百分比 | output |
| 8f9a84ff_71be_4180_b237_22cdd43abc6f | 2#压缩机A相电流 | output |
| bafd3567_9b9c_43dc_9057_b531e733c53d | 2#压缩机B相电流 | output |
| 0847f871_f1d0_4d62_8288_0c47ccf8477b | 2#压缩机C相电流 | output |
| 0f0072ff_d384_4554_b009_69e75bdbddf7 | 3#冷冻泵电压 | output |
| 3b7c16c1_7a98_454a_9a6a_78f410b9fc12 | 3#冷冻泵电流 | output |
| 49f38bdf_e016_4c04_9b80_3ffcc2332ed3 | 3#冷却泵电压 | output |
| 5aed8639_7773_4a0e_b4e7_ee149b62b901 | 3#冷却泵电流 | output |
| 9b93eed9_4eca_4a8b_91c4_ef56d0cb4333 | 3#冷却塔电压 | output |
| 0d04a4a9_edd3_40a9_80ce_885e52787623 | 3#冷却塔电流 | output |
| 97e573de_bbb1_405d_8fcf_6062036f8211 | 4#冷却塔电压 | output |
| 72d4ac6c_e592_443f_bea3_2093a562a623 | 4#冷却塔电流 | output |
| c6731afa_c189_4f29_866d_8b1a6905338a | 3#压缩机电流百分比 | output |
| 82a9e94b_16f3_4906_b14e_389ac3b9acdf | 3#压缩机A相电流 | output |
| fb636b66_f78f_4296_a844_cb077fcef13a | 3#压缩机B相电流 | output |
| b5d1318c_12c3_43d1_b568_669fdcbe558b | 3#压缩机C相电流 | output |
| 9b5bdb29_b693_40fb_837c_7b0e14b780ae | 4#冷冻泵电压 | output |
| 7e91bf2d_dc90_4286_9c8d_dae1dcdb1736 | 4#冷冻泵电流 | output |
| c3fd84e4_9b9b_45ac_a993_d93203553975 | 4#冷却泵电压 | output |
| 11c7e90b_1303_4029_a5f8_a8bf5c640780 | 4#冷却泵电流 | output |
| 5593c817_3be8_4373_8054_88495d7a7057 | 5#冷却塔电压 | output |
| 13e85966_e1b6_43f9_848b_66ac7b6b8046 | 5#冷却塔电流 | output |
| 4d78f278_c743_4d51_820c_bc6823a58a76 | 6#冷却塔电压 | output |
| c953a3b1_95bc_455e_9b27_ca105e8dff63 | 6#冷却塔电流 | output |
| e5b65ddd_0bed_4436_aba2_d5c18f141850 | 4#压缩机电流百分比 | output |
| 3e088f0f_0d68_4379_b76d_2671d48ef2b4 | 4#压缩机A相电流 | output |
| 91bdd4d8_c9ca_44d7_b126_e91b4b798977 | 4#压缩机B相电流 | output |
| 78b88569_0bfb_4d86_9deb_09c6c30fab66 | 4#压缩机C相电流 | output |
| 9aa15548_c1ad_4ae8_9122_4f9ba250361e | 1#冷却泵电压 | output |
| 616cb0c3_5be5_4a8d_955a_883d799a671d | 1#冷却泵电流 | output |
