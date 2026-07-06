/**
 * 短信预览「手机系统界面文案」按收件国家语言本地化。
 * 目的:泰国收件人 → 泰文界面;孟加拉 → 孟加拉文……让截图像当地真机。
 * 未覆盖的语言回退英文。{sender} 为发送人占位符。
 */
export interface PreviewChrome {
  today: string
  unread: string
  tapToLoad: string          // 链接预览加载卡
  noReply: string            // 品牌单向发送人:不可回复提示
  learnMore: string
  textingWith: string        // 号码发送人:正在发送 {sender}
  saveTitle: string          // 保存 {sender}?
  saveSub: string
  reportSpam: string
  addContact: string
  replyOkay: string
  replyThanks: string
  simText: string            // 输入框占位 SIM2 · 短信
  iosSmsLabel: string        // iOS 会话时间上方服务标签
  iosInput: string           // iOS 输入框占位
}

export const PREVIEW_CHROME: Record<string, PreviewChrome> = {
  en: {
    today: 'Today', unread: 'Unread', tapToLoad: 'Tap to load preview',
    noReply: 'The sender cannot receive replies. Contact them directly.', learnMore: 'Learn more',
    textingWith: 'Texting with {sender} (SMS/MMS)', saveTitle: 'Save {sender}?',
    saveSub: 'Saving this number will add a new contact', reportSpam: 'Report spam', addContact: 'Add contact',
    replyOkay: 'Okay', replyThanks: 'Thanks', simText: 'SIM2 · Text',
    iosSmsLabel: 'Text Message', iosInput: 'Text Message',
  },
  zh: {
    today: '今天', unread: '未读', tapToLoad: '轻按即可载入预览画面',
    noReply: '发送者无法接收回复。请直接联系对方。', learnMore: '了解详情',
    textingWith: '正在向 {sender} 发送信息（短信/彩信）', saveTitle: '保存 {sender}？',
    saveSub: '保存该号码将新建一个联系人', reportSpam: '举报垃圾信息', addContact: '添加联系人',
    replyOkay: '好的', replyThanks: '谢谢', simText: 'SIM2 · 短信',
    iosSmsLabel: '信息 · 短信', iosInput: '信息',
  },
  zhHant: {
    today: '今天', unread: '未讀', tapToLoad: '輕按即可載入預覽畫面',
    noReply: '傳送者無法接受回覆。請直接聯絡對方。', learnMore: '瞭解詳情',
    textingWith: '正在與 {sender} 傳送訊息（SMS/MMS）', saveTitle: '儲存 {sender}？',
    saveSub: '儲存這個號碼會新增聯絡人', reportSpam: '檢舉垃圾訊息', addContact: '新增聯絡人',
    replyOkay: '好', replyThanks: '謝謝', simText: 'SIM2 · 訊息',
    iosSmsLabel: '訊息 · 簡訊', iosInput: '訊息',
  },
  th: {
    today: 'วันนี้', unread: 'ยังไม่ได้อ่าน', tapToLoad: 'แตะเพื่อโหลดตัวอย่าง',
    noReply: 'ผู้ส่งไม่สามารถรับการตอบกลับได้ โปรดติดต่อผู้ส่งโดยตรง', learnMore: 'ดูข้อมูลเพิ่มเติม',
    textingWith: 'กำลังส่งข้อความถึง {sender} (SMS/MMS)', saveTitle: 'บันทึก {sender} ไหม',
    saveSub: 'การบันทึกหมายเลขนี้จะเพิ่มรายชื่อติดต่อใหม่', reportSpam: 'รายงานสแปม', addContact: 'เพิ่มรายชื่อติดต่อ',
    replyOkay: 'ตกลง', replyThanks: 'ขอบคุณ', simText: 'SIM2 · ข้อความ',
    iosSmsLabel: 'ข้อความ', iosInput: 'ข้อความ',
  },
  bn: {
    today: 'আজ', unread: 'অপঠিত', tapToLoad: 'প্রিভিউ লোড করতে ট্যাপ করুন',
    noReply: 'প্রেরক উত্তর পেতে পারেন না। সরাসরি যোগাযোগ করুন।', learnMore: 'আরও জানুন',
    textingWith: '{sender}-কে টেক্সট করা হচ্ছে (SMS/MMS)', saveTitle: '{sender} সেভ করবেন?',
    saveSub: 'এই নম্বর সেভ করলে একটি নতুন পরিচিতি যোগ হবে', reportSpam: 'স্প্যাম রিপোর্ট করুন', addContact: 'পরিচিতি যোগ করুন',
    replyOkay: 'ঠিক আছে', replyThanks: 'ধন্যবাদ', simText: 'SIM2 · টেক্সট',
    iosSmsLabel: 'এসএমএস', iosInput: 'টেক্সট মেসেজ',
  },
  pt: {
    today: 'Hoje', unread: 'Não lida', tapToLoad: 'Toque para carregar a pré-visualização',
    noReply: 'O remetente não pode receber respostas. Entre em contato diretamente.', learnMore: 'Saiba mais',
    textingWith: 'Enviando mensagem para {sender} (SMS/MMS)', saveTitle: 'Salvar {sender}?',
    saveSub: 'Salvar este número adicionará um novo contato', reportSpam: 'Denunciar spam', addContact: 'Adicionar contato',
    replyOkay: 'Ok', replyThanks: 'Obrigado', simText: 'SIM2 · Texto',
    iosSmsLabel: 'Mensagem de texto', iosInput: 'Mensagem de texto',
  },
  es: {
    today: 'Hoy', unread: 'No leído', tapToLoad: 'Toca para cargar la vista previa',
    noReply: 'El remitente no puede recibir respuestas. Contáctalo directamente.', learnMore: 'Más información',
    textingWith: 'Enviando mensaje a {sender} (SMS/MMS)', saveTitle: '¿Guardar {sender}?',
    saveSub: 'Guardar este número añadirá un nuevo contacto', reportSpam: 'Reportar spam', addContact: 'Añadir contacto',
    replyOkay: 'De acuerdo', replyThanks: 'Gracias', simText: 'SIM2 · Texto',
    iosSmsLabel: 'Mensaje de texto', iosInput: 'Mensaje de texto',
  },
  vi: {
    today: 'Hôm nay', unread: 'Chưa đọc', tapToLoad: 'Nhấn để tải bản xem trước',
    noReply: 'Người gửi không thể nhận trả lời. Vui lòng liên hệ trực tiếp.', learnMore: 'Tìm hiểu thêm',
    textingWith: 'Đang nhắn tin với {sender} (SMS/MMS)', saveTitle: 'Lưu {sender}?',
    saveSub: 'Lưu số này sẽ thêm một liên hệ mới', reportSpam: 'Báo cáo spam', addContact: 'Thêm liên hệ',
    replyOkay: 'Được', replyThanks: 'Cảm ơn', simText: 'SIM2 · Tin nhắn',
    iosSmsLabel: 'Tin nhắn văn bản', iosInput: 'Tin nhắn văn bản',
  },
  id: {
    today: 'Hari ini', unread: 'Belum dibaca', tapToLoad: 'Ketuk untuk memuat pratinjau',
    noReply: 'Pengirim tidak dapat menerima balasan. Hubungi langsung.', learnMore: 'Pelajari lebih lanjut',
    textingWith: 'Mengirim SMS ke {sender} (SMS/MMS)', saveTitle: 'Simpan {sender}?',
    saveSub: 'Menyimpan nomor ini akan menambahkan kontak baru', reportSpam: 'Laporkan spam', addContact: 'Tambahkan kontak',
    replyOkay: 'Oke', replyThanks: 'Terima kasih', simText: 'SIM2 · Teks',
    iosSmsLabel: 'Pesan Teks', iosInput: 'Pesan teks',
  },
  ar: {
    today: 'اليوم', unread: 'غير مقروء', tapToLoad: 'انقر لتحميل المعاينة',
    noReply: 'لا يمكن للمُرسِل تلقّي الردود. تواصل معه مباشرةً.', learnMore: 'مزيد من المعلومات',
    textingWith: 'مراسلة {sender} ‏(SMS/MMS)', saveTitle: 'حفظ {sender}؟',
    saveSub: 'سيؤدي حفظ هذا الرقم إلى إضافة جهة اتصال جديدة', reportSpam: 'الإبلاغ عن رسالة مزعجة', addContact: 'إضافة جهة اتصال',
    replyOkay: 'حسنًا', replyThanks: 'شكرًا', simText: 'SIM2 · رسالة',
    iosSmsLabel: 'رسالة نصية', iosInput: 'رسالة نصية',
  },
  ru: {
    today: 'Сегодня', unread: 'Непрочитанные', tapToLoad: 'Нажмите, чтобы загрузить превью',
    noReply: 'Отправитель не может получать ответы. Свяжитесь напрямую.', learnMore: 'Подробнее',
    textingWith: 'Переписка с {sender} (SMS/MMS)', saveTitle: 'Сохранить {sender}?',
    saveSub: 'Сохранение номера добавит новый контакт', reportSpam: 'Пожаловаться на спам', addContact: 'Добавить контакт',
    replyOkay: 'Хорошо', replyThanks: 'Спасибо', simText: 'SIM2 · Текст',
    iosSmsLabel: 'Сообщение', iosInput: 'Сообщение',
  },
}

/** 国家 ISO2 → 界面语言 key(未列出的国家回退英文) */
export const COUNTRY_LANG: Record<string, string> = {
  TH: 'th', BD: 'bn', CN: 'zh', TW: 'zhHant', HK: 'zhHant', MO: 'zhHant',
  VN: 'vi', ID: 'id',
  BR: 'pt', PT: 'pt', AO: 'pt', MZ: 'pt',
  ES: 'es', MX: 'es', AR: 'es', CO: 'es', CL: 'es', PE: 'es', VE: 'es', EC: 'es',
  BO: 'es', PY: 'es', GT: 'es', HN: 'es', NI: 'es', CR: 'es', DO: 'es', SV: 'es',
  UY: 'es', PA: 'es', CU: 'es',
  RU: 'ru', BY: 'ru', KZ: 'ru', KG: 'ru',
  AE: 'ar', SA: 'ar', EG: 'ar', IQ: 'ar', JO: 'ar', KW: 'ar', QA: 'ar', OM: 'ar',
  BH: 'ar', LY: 'ar', DZ: 'ar', MA: 'ar', TN: 'ar', SD: 'ar', SY: 'ar', YE: 'ar', LB: 'ar',
}
