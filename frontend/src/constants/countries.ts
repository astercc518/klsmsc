/**
 * 全局国家数据列表
 * iso: ISO 3166-1 alpha-2 国家代码 (如 CN, US, BR)
 * dial: 电话国码 (如 86, 1, 55)
 * name: 中文名称
 * en: 英文名称
 */
export interface CountryItem {
  iso: string
  dial: string
  name: string
  en: string
}

export const COUNTRY_LIST: CountryItem[] = [
  { iso: 'AF', dial: '93', name: '阿富汗', en: 'Afghanistan' },
  { iso: 'AL', dial: '355', name: '阿尔巴尼亚', en: 'Albania' },
  { iso: 'DZ', dial: '213', name: '阿尔及利亚', en: 'Algeria' },
  { iso: 'AO', dial: '244', name: '安哥拉', en: 'Angola' },
  { iso: 'AR', dial: '54', name: '阿根廷', en: 'Argentina' },
  { iso: 'AM', dial: '374', name: '亚美尼亚', en: 'Armenia' },
  { iso: 'AU', dial: '61', name: '澳大利亚', en: 'Australia' },
  { iso: 'AT', dial: '43', name: '奥地利', en: 'Austria' },
  { iso: 'AZ', dial: '994', name: '阿塞拜疆', en: 'Azerbaijan' },
  { iso: 'BH', dial: '973', name: '巴林', en: 'Bahrain' },
  { iso: 'BD', dial: '880', name: '孟加拉国', en: 'Bangladesh' },
  { iso: 'BY', dial: '375', name: '白俄罗斯', en: 'Belarus' },
  { iso: 'BE', dial: '32', name: '比利时', en: 'Belgium' },
  { iso: 'BJ', dial: '229', name: '贝宁', en: 'Benin' },
  { iso: 'BO', dial: '591', name: '玻利维亚', en: 'Bolivia' },
  { iso: 'BA', dial: '387', name: '波黑', en: 'Bosnia' },
  { iso: 'BR', dial: '55', name: '巴西', en: 'Brazil' },
  { iso: 'BN', dial: '673', name: '文莱', en: 'Brunei' },
  { iso: 'BG', dial: '359', name: '保加利亚', en: 'Bulgaria' },
  { iso: 'BF', dial: '226', name: '布基纳法索', en: 'Burkina Faso' },
  { iso: 'KH', dial: '855', name: '柬埔寨', en: 'Cambodia' },
  { iso: 'CM', dial: '237', name: '喀麦隆', en: 'Cameroon' },
  { iso: 'CA', dial: '1', name: '加拿大', en: 'Canada' },
  { iso: 'CL', dial: '56', name: '智利', en: 'Chile' },
  { iso: 'CN', dial: '86', name: '中国', en: 'China' },
  { iso: 'CO', dial: '57', name: '哥伦比亚', en: 'Colombia' },
  { iso: 'CD', dial: '243', name: '刚果(金)', en: 'DR Congo' },
  { iso: 'CR', dial: '506', name: '哥斯达黎加', en: 'Costa Rica' },
  { iso: 'CI', dial: '225', name: '科特迪瓦', en: 'Ivory Coast' },
  { iso: 'HR', dial: '385', name: '克罗地亚', en: 'Croatia' },
  { iso: 'CU', dial: '53', name: '古巴', en: 'Cuba' },
  { iso: 'CY', dial: '357', name: '塞浦路斯', en: 'Cyprus' },
  { iso: 'CZ', dial: '420', name: '捷克', en: 'Czech Republic' },
  { iso: 'DK', dial: '45', name: '丹麦', en: 'Denmark' },
  { iso: 'DO', dial: '1809', name: '多米尼加', en: 'Dominican Republic' },
  { iso: 'EC', dial: '593', name: '厄瓜多尔', en: 'Ecuador' },
  { iso: 'EG', dial: '20', name: '埃及', en: 'Egypt' },
  { iso: 'SV', dial: '503', name: '萨尔瓦多', en: 'El Salvador' },
  { iso: 'EE', dial: '372', name: '爱沙尼亚', en: 'Estonia' },
  { iso: 'ET', dial: '251', name: '埃塞俄比亚', en: 'Ethiopia' },
  { iso: 'FI', dial: '358', name: '芬兰', en: 'Finland' },
  { iso: 'FR', dial: '33', name: '法国', en: 'France' },
  { iso: 'GE', dial: '995', name: '格鲁吉亚', en: 'Georgia' },
  { iso: 'DE', dial: '49', name: '德国', en: 'Germany' },
  { iso: 'GH', dial: '233', name: '加纳', en: 'Ghana' },
  { iso: 'GR', dial: '30', name: '希腊', en: 'Greece' },
  { iso: 'GT', dial: '502', name: '危地马拉', en: 'Guatemala' },
  { iso: 'GN', dial: '224', name: '几内亚', en: 'Guinea' },
  { iso: 'HN', dial: '504', name: '洪都拉斯', en: 'Honduras' },
  { iso: 'HK', dial: '852', name: '香港', en: 'Hong Kong' },
  { iso: 'HU', dial: '36', name: '匈牙利', en: 'Hungary' },
  { iso: 'IS', dial: '354', name: '冰岛', en: 'Iceland' },
  { iso: 'IN', dial: '91', name: '印度', en: 'India' },
  { iso: 'ID', dial: '62', name: '印度尼西亚', en: 'Indonesia' },
  { iso: 'IR', dial: '98', name: '伊朗', en: 'Iran' },
  { iso: 'IQ', dial: '964', name: '伊拉克', en: 'Iraq' },
  { iso: 'IE', dial: '353', name: '爱尔兰', en: 'Ireland' },
  { iso: 'IL', dial: '972', name: '以色列', en: 'Israel' },
  { iso: 'IT', dial: '39', name: '意大利', en: 'Italy' },
  { iso: 'JM', dial: '1876', name: '牙买加', en: 'Jamaica' },
  { iso: 'JP', dial: '81', name: '日本', en: 'Japan' },
  { iso: 'JO', dial: '962', name: '约旦', en: 'Jordan' },
  { iso: 'KZ', dial: '7', name: '哈萨克斯坦', en: 'Kazakhstan' },
  { iso: 'KE', dial: '254', name: '肯尼亚', en: 'Kenya' },
  { iso: 'KR', dial: '82', name: '韩国', en: 'South Korea' },
  { iso: 'KW', dial: '965', name: '科威特', en: 'Kuwait' },
  { iso: 'KG', dial: '996', name: '吉尔吉斯斯坦', en: 'Kyrgyzstan' },
  { iso: 'LA', dial: '856', name: '老挝', en: 'Laos' },
  { iso: 'LV', dial: '371', name: '拉脱维亚', en: 'Latvia' },
  { iso: 'LB', dial: '961', name: '黎巴嫩', en: 'Lebanon' },
  { iso: 'LY', dial: '218', name: '利比亚', en: 'Libya' },
  { iso: 'LT', dial: '370', name: '立陶宛', en: 'Lithuania' },
  { iso: 'LU', dial: '352', name: '卢森堡', en: 'Luxembourg' },
  { iso: 'MO', dial: '853', name: '澳门', en: 'Macao' },
  { iso: 'MG', dial: '261', name: '马达加斯加', en: 'Madagascar' },
  { iso: 'MY', dial: '60', name: '马来西亚', en: 'Malaysia' },
  { iso: 'ML', dial: '223', name: '马里', en: 'Mali' },
  { iso: 'MX', dial: '52', name: '墨西哥', en: 'Mexico' },
  { iso: 'MD', dial: '373', name: '摩尔多瓦', en: 'Moldova' },
  { iso: 'MN', dial: '976', name: '蒙古', en: 'Mongolia' },
  { iso: 'MA', dial: '212', name: '摩洛哥', en: 'Morocco' },
  { iso: 'MZ', dial: '258', name: '莫桑比克', en: 'Mozambique' },
  { iso: 'MM', dial: '95', name: '缅甸', en: 'Myanmar' },
  { iso: 'NP', dial: '977', name: '尼泊尔', en: 'Nepal' },
  { iso: 'NL', dial: '31', name: '荷兰', en: 'Netherlands' },
  { iso: 'NZ', dial: '64', name: '新西兰', en: 'New Zealand' },
  { iso: 'NI', dial: '505', name: '尼加拉瓜', en: 'Nicaragua' },
  { iso: 'NE', dial: '227', name: '尼日尔', en: 'Niger' },
  { iso: 'NG', dial: '234', name: '尼日利亚', en: 'Nigeria' },
  { iso: 'NO', dial: '47', name: '挪威', en: 'Norway' },
  { iso: 'OM', dial: '968', name: '阿曼', en: 'Oman' },
  { iso: 'PK', dial: '92', name: '巴基斯坦', en: 'Pakistan' },
  { iso: 'PA', dial: '507', name: '巴拿马', en: 'Panama' },
  { iso: 'PY', dial: '595', name: '巴拉圭', en: 'Paraguay' },
  { iso: 'PE', dial: '51', name: '秘鲁', en: 'Peru' },
  { iso: 'PH', dial: '63', name: '菲律宾', en: 'Philippines' },
  { iso: 'PL', dial: '48', name: '波兰', en: 'Poland' },
  { iso: 'PT', dial: '351', name: '葡萄牙', en: 'Portugal' },
  { iso: 'QA', dial: '974', name: '卡塔尔', en: 'Qatar' },
  { iso: 'RO', dial: '40', name: '罗马尼亚', en: 'Romania' },
  { iso: 'RU', dial: '7', name: '俄罗斯', en: 'Russia' },
  { iso: 'RW', dial: '250', name: '卢旺达', en: 'Rwanda' },
  { iso: 'SA', dial: '966', name: '沙特阿拉伯', en: 'Saudi Arabia' },
  { iso: 'SN', dial: '221', name: '塞内加尔', en: 'Senegal' },
  { iso: 'RS', dial: '381', name: '塞尔维亚', en: 'Serbia' },
  { iso: 'SG', dial: '65', name: '新加坡', en: 'Singapore' },
  { iso: 'SK', dial: '421', name: '斯洛伐克', en: 'Slovakia' },
  { iso: 'SI', dial: '386', name: '斯洛文尼亚', en: 'Slovenia' },
  { iso: 'SO', dial: '252', name: '索马里', en: 'Somalia' },
  { iso: 'ZA', dial: '27', name: '南非', en: 'South Africa' },
  { iso: 'ES', dial: '34', name: '西班牙', en: 'Spain' },
  { iso: 'LK', dial: '94', name: '斯里兰卡', en: 'Sri Lanka' },
  { iso: 'SD', dial: '249', name: '苏丹', en: 'Sudan' },
  { iso: 'SE', dial: '46', name: '瑞典', en: 'Sweden' },
  { iso: 'CH', dial: '41', name: '瑞士', en: 'Switzerland' },
  { iso: 'SY', dial: '963', name: '叙利亚', en: 'Syria' },
  { iso: 'TW', dial: '886', name: '台湾', en: 'Taiwan' },
  { iso: 'TJ', dial: '992', name: '塔吉克斯坦', en: 'Tajikistan' },
  { iso: 'TZ', dial: '255', name: '坦桑尼亚', en: 'Tanzania' },
  { iso: 'TH', dial: '66', name: '泰国', en: 'Thailand' },
  { iso: 'TN', dial: '216', name: '突尼斯', en: 'Tunisia' },
  { iso: 'TR', dial: '90', name: '土耳其', en: 'Turkey' },
  { iso: 'TM', dial: '993', name: '土库曼斯坦', en: 'Turkmenistan' },
  { iso: 'UG', dial: '256', name: '乌干达', en: 'Uganda' },
  { iso: 'UA', dial: '380', name: '乌克兰', en: 'Ukraine' },
  { iso: 'AE', dial: '971', name: '阿联酋', en: 'UAE' },
  { iso: 'GB', dial: '44', name: '英国', en: 'United Kingdom' },
  { iso: 'US', dial: '1', name: '美国', en: 'United States' },
  { iso: 'UY', dial: '598', name: '乌拉圭', en: 'Uruguay' },
  { iso: 'UZ', dial: '998', name: '乌兹别克斯坦', en: 'Uzbekistan' },
  { iso: 'VE', dial: '58', name: '委内瑞拉', en: 'Venezuela' },
  { iso: 'VN', dial: '84', name: '越南', en: 'Vietnam' },
  { iso: 'YE', dial: '967', name: '也门', en: 'Yemen' },
  { iso: 'ZM', dial: '260', name: '赞比亚', en: 'Zambia' },
  { iso: 'ZW', dial: '263', name: '津巴布韦', en: 'Zimbabwe' },
]

/**
 * 按国码/ISO代码/名称搜索国家
 */
export function searchCountries(query: string): CountryItem[] {
  if (!query) return COUNTRY_LIST
  const q = query.toLowerCase().trim()
  return COUNTRY_LIST.filter(c =>
    c.dial.startsWith(q) ||
    c.iso.toLowerCase().includes(q) ||
    c.name.includes(q) ||
    c.en.toLowerCase().includes(q)
  )
}

/**
 * 通过 ISO 代码查找国家
 */
export function findCountryByIso(iso: string): CountryItem | undefined {
  return COUNTRY_LIST.find(c => c.iso === iso)
}

/**
 * 通过国码查找国家
 */
export function findCountryByDial(dial: string): CountryItem | undefined {
  return COUNTRY_LIST.find(c => c.dial === dial)
}
