
#### stages.json
 list len 120
  keys: ['key', 'act', 'no', 'level', 'type', 'difficulty', 'name', 'waves', 'monsterCount', 'kills', 'goldPerClear', 'expPerClear', 'boss', 'slug']
  sample: {"key": 1101, "act": 1, "no": 1, "level": 1, "type": "NORMAL", "difficulty": "NORMAL", "name": {"zh-Hans": "牧场", "zh-Hant": "牧場", "en-US": "Pasture", "fr-FR": "Pâturage", "de-DE": "Weide", "id-ID": "Padang Rumput", "ja-JP": "牧草地", "ko-KR": "목초지", "pl-PL": "Pastwisko", "pt-BR": "Pasto", "ru-RU": "Пастбище", "es-ES": "Pasto", "th-TH": "ทุ่งหญ้า", "tr-TR": "Otlak", "uk-UA": "Пасовище", "vi-VN": "Đồng cỏ"}, "waves": 10, "monsterCount": 2, "kills": 10, "goldPerClear": 14, "expPerClear": 16, "boss": {
  keys: ['key', 'act', 'no', 'level', 'type', 'difficulty', 'name', 'waves', 'monsterCount', 'kills', 'goldPerClear', 'expPerClear', 'boss', 'slug']
  sample: {"key": 1102, "act": 1, "no": 2, "level": 2, "type": "NORMAL", "difficulty": "NORMAL", "name": {"zh-Hans": "阴影草原", "zh-Hant": "陰影草原", "en-US": "Shadow Meadow", "fr-FR": "Prairie d'Ombre", "de-DE": "Schattenwiese", "id-ID": "Padang Bayangan", "ja-JP": "影の草原", "ko-KR": "그림자 초원", "pl-PL": "Łąka Cieni", "pt-BR": "Prado Sombrio", "ru-RU": "Теневая поляна", "es-ES": "Prado Sombrío", "th-TH": "ทุ่งหญ้าเงา", "tr-TR": "Gölge Çayırı", "uk-UA": "Тінисті луки", "vi-VN": "Đồng cỏ Bóng"}, "waves": 11, "monste

#### farm_stages.json
 list len 108
  keys: ['key', 'label', 'act', 'stageNo', 'level', 'difficulty', 'name', 'waves', 'perWave', 'monsterTypes', 'count', 'totalHP', 'expectedGold', 'expectedEXP', 'goldPerHP', 'expPerHP']
  sample: {"key": 1101, "label": "1-1", "act": 1, "stageNo": 1, "level": 1, "difficulty": "NORMAL", "name": {"zh-Hans": "牧场", "zh-Hant": "牧場", "en-US": "Pasture", "fr-FR": "Pâturage", "de-DE": "Weide", "id-ID": "Padang Rumput", "ja-JP": "牧草地", "ko-KR": "목초지", "pl-PL": "Pastwisko", "pt-BR": "Pasto", "ru-RU": "Пастбище", "es-ES": "Pasto", "th-TH": "ทุ่งหญ้า", "tr-TR": "Otlak", "uk-UA": "Пасовище", "vi-VN": "Đồng cỏ"}, "waves": 10, "perWave": 1, "monsterTypes": 2, "count": 10, "totalHP": 56, "expectedGold": 
  keys: ['key', 'label', 'act', 'stageNo', 'level', 'difficulty', 'name', 'waves', 'perWave', 'monsterTypes', 'count', 'totalHP', 'expectedGold', 'expectedEXP', 'goldPerHP', 'expPerHP']
  sample: {"key": 1102, "label": "1-2", "act": 1, "stageNo": 2, "level": 2, "difficulty": "NORMAL", "name": {"zh-Hans": "阴影草原", "zh-Hant": "陰影草原", "en-US": "Shadow Meadow", "fr-FR": "Prairie d'Ombre", "de-DE": "Schattenwiese", "id-ID": "Padang Bayangan", "ja-JP": "影の草原", "ko-KR": "그림자 초원", "pl-PL": "Łąka Cieni", "pt-BR": "Prado Sombrio", "ru-RU": "Теневая поляна", "es-ES": "Prado Sombrío", "th-TH": "ทุ่งหญ้าเงา", "tr-TR": "Gölge Çayırı", "uk-UA": "Тінисті луки", "vi-VN": "Đồng cỏ Bóng"}, "waves": 11, "per

#### portal_map.json
 dict len 3 first keys: ['1', '2', '3']
  [1]: [{"no": 1, "x": 0.4883, "y": 0.9105}, {"no": 2, "x": 0.5617, "y": 0.8407}, {"no": 3, "x": 0.595, "y": 0.757}, {"no": 4, "x": 0.6083, "y": 0.6686}, {"no": 5, "x": 0.595, "y": 0.5802}, {"no": 6, "x": 0.5517, "y": 0.5012}, {"no": 7, "x": 0.505, "y": 0.4221}, {"no": 8, "x": 0.4283, "y": 0.3523}, {"no": 9, "x": 0.3417, "y": 0.2919}, {"no": 10, "x": 0.4688, "y": 0.228, "boss": true}]
  [2]: [{"no": 1, "x": 0.4483, "y": 0.8826}, {"no": 2, "x": 0.535, "y": 0.8128}, {"no": 3, "x": 0.5817, "y": 0.7291}, {"no": 4, "x": 0.6683, "y": 0.6547}, {"no": 5, "x": 0.555, "y": 0.6128}, {"no": 6, "x": 0.4683, "y": 0.5384}, {"no": 7, "x": 0.435, "y": 0.4547}, {"no": 8, "x": 0.515, "y": 0.3802}, {"no": 9, "x": 0.535, "y": 0.2919}, {"no": 10, "x": 0.535, "y": 0.2034, "boss": true}]

#### monsters.json
 list len 61
  keys: ['MonsterKey', 'MonsterNameStringKey', 'MonsterNameStringKey_i18n', 'MONSTERTYPE', 'RewardGold', 'RewardExp', 'SkillKey', 'AttackDamage', 'AttackSpeed', 'MaxLife', 'MovementSpeed', 'DeadSoundKey', 'PrefabPath', 'AnimatorPath', 'portrait', 'sprite_folder', 'skill_name_i18n', 'attack', 'attacks', 'attackElements', 'stages', 'slug']
  sample: {"MonsterKey": 10011, "MonsterNameStringKey": "MonsterName_10011", "MonsterNameStringKey_i18n": {"zh-Hans": "史莱姆", "zh-Hant": "史萊姆", "en-US": "Slime", "fr-FR": "Slime", "de-DE": "Schleim", "id-ID": "Slime", "ja-JP": "スライム", "ko-KR": "슬라임", "pl-PL": "Szlam", "pt-BR": "Slime", "ru-RU": "Слизь", "es-ES": "Limo", "th-TH": "สไลม์", "tr-TR": "Balçık", "uk-UA": "Слиз", "vi-VN": "Slime"}, "MONSTERTYPE": "MONSTER", "RewardGold": 10, "RewardExp": 10, "SkillKey": 100111, "AttackDamage": 10, "AttackSpeed": 
  keys: ['MonsterKey', 'MonsterNameStringKey', 'MonsterNameStringKey_i18n', 'MONSTERTYPE', 'RewardGold', 'RewardExp', 'SkillKey', 'AttackDamage', 'AttackSpeed', 'MaxLife', 'MovementSpeed', 'DeadSoundKey', 'PrefabPath', 'AnimatorPath', 'portrait', 'sprite_folder', 'skill_name_i18n', 'attack', 'attacks', 'attackElements', 'stages', 'slug']
  sample: {"MonsterKey": 10021, "MonsterNameStringKey": "MonsterName_10021", "MonsterNameStringKey_i18n": {"zh-Hans": "哥布林", "zh-Hant": "哥布林", "en-US": "Goblin", "fr-FR": "Gobelin", "de-DE": "Goblin", "id-ID": "Goblin", "ja-JP": "ゴブリン", "ko-KR": "고블린", "pl-PL": "Goblin", "pt-BR": "Goblin", "ru-RU": "Гоблин", "es-ES": "Goblin", "th-TH": "ก็อบลิน", "tr-TR": "Goblin", "uk-UA": "Гоблін", "vi-VN": "Goblin"}, "MONSTERTYPE": "MONSTER", "RewardGold": 12, "RewardExp": 12, "SkillKey": 100211, "AttackDamage": 15, "A

#### status_effects.json
 list len 6
  keys: ['StatusEffectKey', 'StatusEffectType', 'Duration', 'BuffKeys', 'OverrideType', 'Param0', 'Param1', 'Param2', 'Param3', 'buffs', 'slug']
  sample: {"StatusEffectKey": 101, "StatusEffectType": "Chill", "Duration": 400, "BuffKeys": "1011 1012", "OverrideType": "InitDuration", "Param0": null, "Param1": null, "Param2": null, "Param3": null, "buffs": [{"BuffKey": 1011, "BuffType": "Debuff", "STATTYPE": "AttackSpeed", "MODTYPE": "MULTIPLICATIVE", "Value": 300}, {"BuffKey": 1012, "BuffType": "Debuff", "STATTYPE": "MovementSpeed", "MODTYPE": "MULTIPLICATIVE", "Value": 300}], "slug": "chill"}
  keys: ['StatusEffectKey', 'StatusEffectType', 'Duration', 'BuffKeys', 'OverrideType', 'Param0', 'Param1', 'Param2', 'Param3', 'buffs', 'slug']
  sample: {"StatusEffectKey": 102, "StatusEffectType": "Freeze", "Duration": 150, "BuffKeys": null, "OverrideType": "NotOverride", "Param0": null, "Param1": null, "Param2": null, "Param3": null, "buffs": [], "slug": "freeze"}

#### buffs.json
 list len 29
  keys: ['BuffKey', 'BuffType', 'STATTYPE', 'MODTYPE', 'Value']
  sample: {"BuffKey": 1011, "BuffType": "Debuff", "STATTYPE": "AttackSpeed", "MODTYPE": "MULTIPLICATIVE", "Value": 300}
  keys: ['BuffKey', 'BuffType', 'STATTYPE', 'MODTYPE', 'Value']
  sample: {"BuffKey": 1012, "BuffType": "Debuff", "STATTYPE": "MovementSpeed", "MODTYPE": "MULTIPLICATIVE", "Value": 300}

#### runes.json
 list len 197
  keys: ['RuneKey', 'NameKey', 'NameKey_i18n', 'MaxLevel', 'PrevNodeRequiredLevel', 'NextRuneKey', 'PreviewRuneKey', 'LevelDataKey', 'IconPath', 'icon', 'next_runes', 'slug']
  sample: {"RuneKey": 1, "NameKey": "RuneName_AllHeroAttackDamage", "NameKey_i18n": {"zh-Hans": "战争符文", "zh-Hant": "戰爭符文", "en-US": "Rune of War", "fr-FR": "Rune de Guerre", "de-DE": "Kriegsrune", "id-ID": "Rune Perang", "ja-JP": "戦争のルーン", "ko-KR": "전쟁의 룬", "pl-PL": "Runa Wojny", "pt-BR": "Runa de Guerra", "ru-RU": "Руна войны", "es-ES": "Runa de Guerra", "th-TH": "รูนสงคราม", "tr-TR": "Savaş Runu", "uk-UA": "Руна війни", "vi-VN": "Rune Chiến Tranh"}, "MaxLevel": 1, "PrevNodeRequiredLevel": null, "NextRun
  keys: ['RuneKey', 'NameKey', 'NameKey_i18n', 'MaxLevel', 'PrevNodeRequiredLevel', 'NextRuneKey', 'PreviewRuneKey', 'LevelDataKey', 'IconPath', 'icon', 'next_runes', 'slug']
  sample: {"RuneKey": 10, "NameKey": "RuneName_AdditionalGoldStageBoss", "NameKey_i18n": {"zh-Hans": "财富符文", "zh-Hant": "財富符文", "en-US": "Rune of Wealth", "fr-FR": "Rune de Richesse", "de-DE": "Reichtumsrune", "id-ID": "Rune Kekayaan", "ja-JP": "富のルーン", "ko-KR": "재물의 룬", "pl-PL": "Runa Bogactwa", "pt-BR": "Runa da Riqueza", "ru-RU": "Руна богатства", "es-ES": "Runa de Riqueza", "th-TH": "รูนทรัพย์", "tr-TR": "Servet Runu", "uk-UA": "Руна багатства", "vi-VN": "Rune Tài Lộc"}, "MaxLevel": 3, "PrevNodeRequir

#### rune_tree.json
 dict len 4 first keys: ['startNodes', 'bounds', 'nodes', 'edges']
  [startNodes]: [1]
  [bounds]: {"minX": -864.0, "maxX": 1512.0, "minY": -648.0, "maxY": 432.0}

#### skills.json
 list len 106
  keys: ['SkillKey', 'SkillNameKey', 'SkillDescriptionKey', 'ACTIVATIONTYPE', 'ActivationValue', 'SLOTTYPE', 'SkillBuffType', 'BuffGroupKey', 'Param1', 'Param2', 'Param3', 'Param4', 'Param5', 'Range', 'Order', 'DamageType', 'DamageDeliveryType', 'Value', 'SkillLevelKey', 'AnimClipPath1', 'AnimClipPath2', 'AnimClipPath3', 'AttributeKey', 'SoundKey', 'levels', 'slug']
  sample: {"SkillKey": 10001, "SkillNameKey": null, "SkillDescriptionKey": null, "ACTIVATIONTYPE": "BASEATTACK", "ActivationValue": 0, "SLOTTYPE": "BASEATTACK", "SkillBuffType": "Normal", "BuffGroupKey": null, "Param1": 600, "Param2": 200, "Param3": 200, "Param4": null, "Param5": null, "Range": 140, "Order": 999, "DamageType": "Physical", "DamageDeliveryType": "Melee", "Value": 1000, "SkillLevelKey": null, "AnimClipPath1": "Animation/Skill/Skill_10001", "AnimClipPath2": "Animation/Skill/Skill_10001_2", "A
  keys: ['SkillKey', 'SkillNameKey', 'SkillNameKey_i18n', 'SkillDescriptionKey', 'SkillDescriptionKey_i18n', 'ACTIVATIONTYPE', 'ActivationValue', 'SLOTTYPE', 'SkillBuffType', 'BuffGroupKey', 'Param1', 'Param2', 'Param3', 'Param4', 'Param5', 'Range', 'Order', 'DamageType', 'DamageDeliveryType', 'Value', 'SkillLevelKey', 'AnimClipPath1', 'AnimClipPath2', 'AnimClipPath3', 'AttributeKey', 'SoundKey', 'levels', 'slug']
  sample: {"SkillKey": 10101, "SkillNameKey": "SkillName_10101", "SkillNameKey_i18n": {"zh-Hans": "穿透突刺", "zh-Hant": "穿透突刺", "en-US": "Piercing Thrust", "fr-FR": "Estoc Perçant", "de-DE": "Durchstoß", "id-ID": "Tusukan Tembus", "ja-JP": "貫通突き", "ko-KR": "관통 찌르기", "pl-PL": "Przebijające Pchnięcie", "pt-BR": "Estocada Perfurante", "ru-RU": "Пронзающий удар", "es-ES": "Estocada Perforante", "th-TH": "แทงทะลุ", "tr-TR": "Delici İtme", "uk-UA": "Пронизуючий удар", "vi-VN": "Đâm Xuyên"}, "SkillDescriptionKey": 

#### passive_skills.json
 list len 108
  keys: ['PassiveSkillKey', 'SkillNameKey', 'SkillNameKey_i18n', 'STATTYPE', 'MODTYPE', 'Value', 'slug']
  sample: {"PassiveSkillKey": 101001, "SkillNameKey": "Passive_AttackDamage", "SkillNameKey_i18n": {"zh-Hans": "攻击力强化", "zh-Hant": "攻擊力強化", "en-US": "Attack Damage Enhancement", "fr-FR": "Amélioration Dégâts d'Attaque", "de-DE": "Angriffsschadenverstärkung", "id-ID": "Peningkatan Kerusakan Serangan", "ja-JP": "攻撃力強化", "ko-KR": "공격력 강화", "pl-PL": "Wzmocnienie Obrażeń", "pt-BR": "Aprimoramento de Dano de Ataque", "ru-RU": "Усиление урона атаки", "es-ES": "Mejora de Daño de Ataque", "th-TH": "เสริมการโจมตี",
  keys: ['PassiveSkillKey', 'SkillNameKey', 'SkillNameKey_i18n', 'STATTYPE', 'MODTYPE', 'Value', 'slug']
  sample: {"PassiveSkillKey": 101002, "SkillNameKey": "Passive_MaxHp", "SkillNameKey_i18n": {"zh-Hans": "生命强化", "zh-Hant": "生命強化", "en-US": "Health Enhancement", "fr-FR": "Amélioration Santé", "de-DE": "Lebensverstärkung", "id-ID": "Peningkatan HP", "ja-JP": "体力強化", "ko-KR": "체력 강화", "pl-PL": "Wzmocnienie Zdrowia", "pt-BR": "Aprimoramento de Vida", "ru-RU": "Усиление здоровья", "es-ES": "Mejora de Salud", "th-TH": "เสริมHP", "tr-TR": "Sağlık Güçlendirme", "uk-UA": "Посилення здоров'я", "vi-VN": "Tăng cườn

#### catalog.json
 list len 45
  keys: ['name', 'label', 'group', 'rows', 'columns', 'i18nFields', 'hasIcon', 'route']
  sample: {"name": "heroes", "label": "Heroes", "group": "Heroes & Combat", "rows": 6, "columns": ["HeroKey", "HeroNameKey", "HeroNameKey_i18n", "DescriptionKey", "DescriptionKey_i18n", "ClassType", "MainWeaponGearType", "SubWeaponGearType", "SkillKey", "AttackDamage", "AttackSpeed", "CastSpeed", "CriticalChance", "CriticalDamage", "MaxHp", "Armor", "CooldownReduction", "MovementSpeed", "UnlockCost", "IsAvailable", "IsFirstAvailable", "SelectSoundKey", "DeadSoundKey", "DLCAppId", "DLCBitIndex", "HasDLCDro
  keys: ['name', 'label', 'group', 'rows', 'columns', 'i18nFields', 'hasIcon', 'route']
  sample: {"name": "monsters", "label": "Monsters", "group": "Heroes & Combat", "rows": 61, "columns": ["MonsterKey", "MonsterNameStringKey", "MonsterNameStringKey_i18n", "MONSTERTYPE", "RewardGold", "RewardExp", "SkillKey", "AttackDamage", "AttackSpeed", "MaxLife", "MovementSpeed", "DeadSoundKey", "PrefabPath", "AnimatorPath", "portrait", "sprite_folder", "skill_name_i18n", "attack", "attacks", "attackElements", "stages"], "i18nFields": ["MonsterNameStringKey_i18n", "skill_name_i18n"], "hasIcon": true, "

#### slugmap.json
 dict len 5 first keys: ['items', 'stages', 'skills', 'monsters', 'runes']
  [items]: {"910011": "normal-monster-box-1", "910051": "normal-monster-box-2", "910101": "normal-monster-box-3", "910151": "normal-monster-box-lv15", "910201": "normal-monster-box-lv20", "910251": "normal-monster-box-lv25", "910301": "normal-monster-box-lv30", "910351": "normal-monster-box-lv35", "910401": "normal-monster-box-lv40", "910451": "normal-monster-box-lv45", "910501": "normal-monster-box-lv50", "910551": "normal-monster-box-lv55", "910601": "normal-monster-box-lv60", "910651": "normal-monster-b
  [stages]: {"1101": "1101-pasture", "1102": "1102-shadow-meadow", "1103": "1103-wasteland", "1104": "1104-eerie-canyon", "1105": "1105-burning-village-entrance", "1106": "1106-rumstreet-square", "1107": "1107-city-outskirts", "1108": "1108-cemetery", "1109": "1109-cursed-land", "1110": "1110-throne-of-darkness", "1201": "1201-oasis-road", "1202": "1202-sandstorm-valley", "1203": "1203-desert-underground-cave", "1204": "1204-bug-nest", "1205": "1205-scorching-dunes", "1206": "1206-sunset-ruins", "1207": "12

#### recipes.json
 dict len 5 first keys: ['synthesis', 'crafting', 'cube', 'extraction', 'cubeInfo']
  [synthesis]: [{"key": 10100110, "tier": 1, "type": "Gear", "grade": "COMMON", "materialAmount": 9, "minMaterialTier": 1, "avgLevel": 1, "resultLevel": [1, 1]}, {"key": 10100111, "tier": 1, "type": "Gear", "grade": "UNCOMMON", "materialAmount": 9, "minMaterialTier": 1, "avgLevel": 1, "resultLevel": [1, 1]}, {"key": 10100112, "tier": 1, "type": "Gear", "grade": "RARE", "materialAmount": 9, "minMaterialTier": 1, "avgLevel": 1, "resultLevel": [1, 1]}, {"key": 10100113, "tier": 1, "type": "Gear", "grade": "LEGEND
  [crafting]: [{"key": 6001001, "type": "MainWeapon", "tier": 1, "materials": [{"id": 140003, "name": {"zh-Hans": "皮革", "zh-Hant": "皮革", "en-US": "Leather", "fr-FR": "Cuir", "de-DE": "Leder", "id-ID": "Kulit", "ja-JP": "レザー", "ko-KR": "가죽", "pl-PL": "Skóra", "pt-BR": "Couro", "ru-RU": "Кожа", "es-ES": "Cuero", "th-TH": "หนัง", "tr-TR": "Deri", "uk-UA": "Шкіра", "vi-VN": "Da"}, "icon": "/game/items/materials/Item_140003.png", "slug": "leather", "grade": "COMMON", "count": 1}], "result": {"gradeOdds": [{"grade"

#### offering.json
 dict len 5 first keys: ['unlockCubeLevel', 'info', 'gradeOrder', 'alchemyGold', 'coins']
  [unlockCubeLevel]: 20
  [info]: {"zh-Hans": "奉献纪念硬币以获得随机物品。", "zh-Hant": "奉獻紀念硬幣以獲得隨機物品。", "en-US": "Offer commemorative coins to\nobtain random items.", "fr-FR": "Offrez des pièces commémoratives\npour obtenir des objets aléatoires.", "de-DE": "Opfere Gedenkmünzen, um\nzufällige Items zu erhalten.", "id-ID": "Persembahkan koin peringatan\nuntuk mendapat item acak.", "ja-JP": "記念コインを捧げてランダムアイテムを獲得します。", "ko-KR": "기념 주화를 바쳐 무작위 아이템을 얻습니다.", "pl-PL": "Ofiaruj pamiątkowe monety, aby otrzymać losowe przedmioty.", "pt-BR": "Ofereça

#### mechanics.json
 dict len 11 first keys: ['statTypes', 'modTypes', 'modSources', 'damageTypes', 'damageElements', 'statusEffects']
  [statTypes]: ["AttackDamage", "AttackSpeed", "CriticalChance", "CriticalDamage", "MaxHp", "Armor", "MovementSpeed", "AreaOfEffect", "BaseAttackCountReduction", "CooldownReduction", "SkillRangeExpansion", "FireResistance", "ColdResistance", "LightningResistance", "ChaosResistance", "DodgeChance", "BlockChance", "MaxDodgeChance", "MaxBlockChance", "Multistrike", "HpLeech", "ProjectileCount", "HpRegenPerSec", "PhysicalDamagePercent", "FireDamagePercent", "ColdDamagePercent", "LightningDamagePercent", "ChaosDama
  [modTypes]: ["FLAT", "ADDITIVE", "MULTIPLICATIVE"]

#### t/pets.json
 list len 8
  keys: ['PetKey', 'NameKey', 'NameKey_i18n', 'DescriptionKey', 'DescriptionKey_i18n', 'StatDataKey', 'UnlockCondition', 'Param1', 'Param2']
  sample: {"PetKey": 1001, "NameKey": "PetName_1001", "NameKey_i18n": {"zh-Hans": "蝙蝠", "zh-Hant": "蝙蝠", "en-US": "Bat", "fr-FR": "Chauve-souris", "de-DE": "Fledermaus", "id-ID": "Kelelawar", "ja-JP": "コウモリ", "ko-KR": "박쥐", "pl-PL": "Nietoperz", "pt-BR": "Morcego", "ru-RU": "Летучая мышь", "es-ES": "Murciélago", "th-TH": "ค้างคาว", "tr-TR": "Yarasa", "uk-UA": "Кажан", "vi-VN": "Dơi"}, "DescriptionKey": "PetDescription_1001", "DescriptionKey_i18n": {"zh-Hans": "击败蝙蝠", "zh-Hant": "擊敗蝙蝠", "en-US": "Defeat Ba
  keys: ['PetKey', 'NameKey', 'NameKey_i18n', 'DescriptionKey', 'DescriptionKey_i18n', 'StatDataKey', 'UnlockCondition', 'Param1', 'Param2']
  sample: {"PetKey": 1002, "NameKey": "PetName_1002", "NameKey_i18n": {"zh-Hans": "监视者", "zh-Hant": "監視者", "en-US": "Watcher", "fr-FR": "Veilleur", "de-DE": "Wächter", "id-ID": "Pengawas", "ja-JP": "監視者", "ko-KR": "감시자", "pl-PL": "Strażnik", "pt-BR": "Vigia", "ru-RU": "Наблюдатель", "es-ES": "Vigilante", "th-TH": "ผู้เฝ้าดู", "tr-TR": "Gözcü", "uk-UA": "Спостерігач", "vi-VN": "Kẻ Canh Gác"}, "DescriptionKey": "PetDescription_1002", "DescriptionKey_i18n": {"zh-Hans": "击败巨型苍蝇", "zh-Hant": "擊敗巨型蒼蠅", "en-US":

#### t/pet_stats.json
 list len 11
  keys: ['PetStatKey', 'STATTYPE', 'MODTYPE', 'Value']
  sample: {"PetStatKey": 1001, "STATTYPE": "DropChanceNormalChestPercent", "MODTYPE": "FLAT", "Value": 100}
  keys: ['PetStatKey', 'STATTYPE', 'MODTYPE', 'Value']
  sample: {"PetStatKey": 1001, "STATTYPE": "IncreaseExpAmount", "MODTYPE": "FLAT", "Value": 150}

#### t/materials.json
 list len 125
  keys: ['ItemKey', 'MATERIALTYPE', 'StatModGroupKey']
  sample: {"ItemKey": 110001, "MATERIALTYPE": "DECORATION", "StatModGroupKey": 1100011}
  keys: ['ItemKey', 'MATERIALTYPE', 'StatModGroupKey']
  sample: {"ItemKey": 110002, "MATERIALTYPE": "DECORATION", "StatModGroupKey": 1100021}

#### t/currencies.json
 list len 1
  keys: ['CurrencyKey', 'CurrencyNameStringKey', 'CurrencyNameStringKey_i18n', 'Description', 'InitialAmount', 'IconPath']
  sample: {"CurrencyKey": 100001, "CurrencyNameStringKey": "CurrencyName_100001", "CurrencyNameStringKey_i18n": {"zh-Hans": "金币", "zh-Hant": "金幣", "en-US": "Gold", "fr-FR": "Or", "de-DE": "Gold", "id-ID": "Emas", "ja-JP": "ゴールド", "ko-KR": "골드", "pl-PL": "Złoto", "pt-BR": "Ouro", "ru-RU": "Золото", "es-ES": "Oro", "th-TH": "ทอง", "tr-TR": "Altın", "uk-UA": "Золото", "vi-VN": "Vàng"}, "Description": "기본화폐", "InitialAmount": 100, "IconPath": "UI/Icon/Item/Item_100001"}

#### t/cube_recipes.json
 list len 8
  keys: ['CubeKey', 'RECIPETYPE', 'Index', 'IsDefaultUnlocked', 'TooltipStringKey', 'TooltipStringKey_i18n']
  sample: {"CubeKey": 100001, "RECIPETYPE": "SYNTHESIS", "Index": 0, "IsDefaultUnlocked": true, "TooltipStringKey": "Cube_RecipeTooltip_Synthesis", "TooltipStringKey_i18n": {"zh-Hans": "合成 9 件同等级装备,获得更高等级的装备。", "zh-Hant": "合成 9 件同等級裝備,獲得更高等級的裝備。", "en-US": "Synthesize 9 items of the same grade<br>into one of a higher grade.", "fr-FR": "Synthétisez 9 objets du même grade\npour en obtenir un de grade supérieur.", "de-DE": "Kombiniere 9 Gegenstände\nderselben Stufe zu einem höherstufigen.", "id-ID": "Sintesi
  keys: ['CubeKey', 'RECIPETYPE', 'Index', 'IsDefaultUnlocked', 'TooltipStringKey', 'TooltipStringKey_i18n']
  sample: {"CubeKey": 200001, "RECIPETYPE": "ALCHEMY", "Index": 1, "IsDefaultUnlocked": null, "TooltipStringKey": "Cube_RecipeTooltip_Alchemy", "TooltipStringKey_i18n": {"zh-Hans": "将任何物品转换为金币。<br><br>- <color=#F5D958>材料</color>：任意1~9个物品<br>- <color=#30FF63>结果</color>：物品消耗，获得金币", "zh-Hant": "將任何物品轉換為金幣。<br><br>- <color=#F5D958>材料</color>：任意1~9個物品<br>- <color=#30FF63>結果</color>：物品消耗，獲得金幣", "en-US": "Convert any item into gold.<br><br>- <color=#F5D958>Materials</color> : Any 1~9 items<br>- <color=#30FF63>Re

#### t/stat_mods.json
 list len 620
  keys: ['StatModKey', 'Tier', 'STATTYPE', 'MODTYPE', 'MinValue', 'MaxValue', 'Interval']
  sample: {"StatModKey": 100101, "Tier": 1, "STATTYPE": "AttackDamage", "MODTYPE": "FLAT", "MinValue": 1, "MaxValue": 2, "Interval": 1}
  keys: ['StatModKey', 'Tier', 'STATTYPE', 'MODTYPE', 'MinValue', 'MaxValue', 'Interval']
  sample: {"StatModKey": 100101, "Tier": 2, "STATTYPE": "AttackDamage", "MODTYPE": "FLAT", "MinValue": 2, "MaxValue": 3, "Interval": 1}

#### items_detail.json
 dict len 5944 first keys: ['910011', '910051', '910101', '910151', '910201', '910251']
  [910011]: {"desc": null, "stats": null, "synthType": null, "dropKey": 9100111, "uniqueMod": null}
  [910051]: {"desc": null, "stats": null, "synthType": null, "dropKey": 9100511, "uniqueMod": null}

BOXES count: 59 ids: ['910011', '910051', '910101', '910151', '910201', '910251'] ...

#### boxes/910011.json
 dict len 2 first keys: ['table', 'stages']
  [table]: {"dropKey": 9100111, "dropType": "EachDropOneWeight_DLCVariant", "entries": [{"type": "ITEMGROUP", "pct": 31.475, "pcts": {"base": 38.907, "hunter": 34.798, "slayer": 34.798, "both": 31.475}, "hero": null, "item": null, "group": {"id": 1002010, "name": "Common Helmet Lv1", "name_i18n": {"de-DE": "Gewöhnlich Helm Lv1", "en-US": "Common Helmet Lv1", "es-ES": "Común Casco Lv1", "fr-FR": "Commun Casque Lv1", "id-ID": "Biasa Helm Lv1", "ja-JP": "コモン ヘルメット Lv1", "ko-KR": "일반 투구 Lv1", "pl-PL": "Zwykły 
  [stages]: [{"key": 1101, "act": 1, "no": 1, "difficulty": "NORMAL", "type": "NORMAL", "via": "monster", "rate": 160}, {"key": 1102, "act": 1, "no": 2, "difficulty": "NORMAL", "type": "NORMAL", "via": "monster", "rate": 160}, {"key": 1103, "act": 1, "no": 3, "difficulty": "NORMAL", "type": "NORMAL", "via": "monster", "rate": 160}]

#### boxes/920002.json
 dict len 2 first keys: ['table', 'stages']
  [table]: {"dropKey": 9200021, "dropType": "EachDropOneWeight", "entries": [{"type": "ITEM", "pct": 100.0, "pcts": {"base": 100.0, "hunter": 100.0, "slayer": 100.0, "both": 100.0}, "hero": null, "item": {"id": 310001, "name": {"zh-Hans": "短弓", "zh-Hant": "短弓", "en-US": "Short Bow", "fr-FR": "Arc Court", "de-DE": "Kurzbogen", "id-ID": "Busur Pendek", "ja-JP": "ショートボウ", "ko-KR": "단궁", "pl-PL": "Krótki Łuk", "pt-BR": "Arco Curto", "ru-RU": "Короткий Лук", "es-ES": "Arco Corto", "th-TH": "ธนูสั้น", "tr-TR": "
  [stages]: []
