(function () {
  const markdown = `# Счёт INV-2048

**Тип документа:** Счёт на оплату
**Язык:** Английский
**Статус проверки:** Требует проверки

## Поля
| Поле          | Значение                   |
| ------------- | -------------------------- |
| Поставщик    | Northwind Office Supplies  |
| Номер счёта  | INV-2048                   |
| Дата выпуска | 2026-06-12                 |
| Итого        | USD 1,284.40               |

## Позиции
| Описание               | Кол-во | Цена   | Сумма  |
| ---------------------- | ------ | ------ | ------ |
| Archive boxes          | 12     | 18.50  | 222.00 |
| Scanner maintenance    | 1      | 390.00 | 390.00 |
| Document folders       | 40     | 6.10   | 244.00 |
| Intake form packs      | 30     | 7.13   | 214.00 |

## Предупреждения
- Низкая уверенность для поля Tax total.
- Обнаружена рукописная отметка, реконструкция макета пока не выполняется.
`;

  const currentJob = {
    id: "job-demo-invoice",
    fileName: "invoice_inv_2048.png",
    documentType: "Счёт на оплату",
    status: "needs_review",
    statusLabel: "Требует проверки",
    createdAt: "2026-06-20 13:42",
    warningCount: 2,
    metadata: {
      language: "Английский",
      pages: "1",
      validationStatus: "Требует проверки",
      fieldCount: "8",
      tableCount: "1",
      confidence: "88%",
    },
    fields: [
      { label: "Поставщик", value: "Northwind Office Supplies", confidence: "96%", notes: "Чёткий печатный текст" },
      { label: "Номер счёта", value: "INV-2048", confidence: "94%", notes: "Поле в шапке документа" },
      { label: "Дата выпуска", value: "2026-06-12", confidence: "91%", notes: "Дата нормализована" },
      { label: "Дата оплаты", value: "2026-07-12", confidence: "89%", notes: "Выведено из условий оплаты" },
      { label: "Подытог", value: "USD 1,070.00", confidence: "87%", notes: "Согласуется со строками таблицы" },
      { label: "Налог", value: "USD 214.40", confidence: "63%", notes: "Нужна проверка человеком" },
      { label: "Итого", value: "USD 1,284.40", confidence: "92%", notes: "Напечатано в нижней части" },
      { label: "Условия оплаты", value: "Net 30", confidence: "84%", notes: "Мелкий текст" },
    ],
    warnings: [
      {
        severity: "Средний",
        code: "LOW_CONFIDENCE_FIELD",
        target: "Налог",
        message: "Поле читается, но уверенность ниже порога для автоматического принятия.",
      },
      {
        severity: "Низкий",
        code: "HANDWRITTEN_NOTE",
        target: "Отметка согласования",
        message: "Обнаружена рукописная отметка. Восстановление макета отмечено как будущая функция.",
      },
    ],
    tables: [
      {
        name: "Позиции счёта",
        columns: ["Описание", "Кол-во", "Цена", "Сумма"],
        rows: [
          ["Archive boxes", "12", "18.50", "222.00"],
          ["Scanner maintenance", "1", "390.00", "390.00"],
          ["Document folders", "40", "6.10", "244.00"],
          ["Intake form packs", "30", "7.13", "214.00"],
        ],
      },
    ],
    rawText:
      "NORTHWIND OFFICE SUPPLIES\nInvoice INV-2048\nIssue date: 2026-06-12\nPayment terms: Net 30\n\nArchive boxes      12   18.50   222.00\nScanner maintenance 1  390.00   390.00\nDocument folders   40    6.10   244.00\nIntake form packs  30    7.13   214.00\n\nSubtotal: USD 1,070.00\nTax total: USD 214.40\nTotal: USD 1,284.40\n\nApproved for demo review.",
    markdown,
  };

  const jobs = [
    currentJob,
    {
      ...currentJob,
      id: "job-demo-delivery-note",
      fileName: "delivery_note_117.pdf",
      documentType: "Накладная",
      status: "complete",
      statusLabel: "Готово",
      createdAt: "2026-06-19 17:08",
      warningCount: 0,
      metadata: {
        ...currentJob.metadata,
        validationStatus: "Проверка пройдена",
        confidence: "94%",
      },
      warnings: [],
    },
    {
      ...currentJob,
      id: "job-demo-application-form",
      fileName: "application_form_sample.jpg",
      documentType: "Заявление",
      status: "needs_review",
      statusLabel: "Требует проверки",
      createdAt: "2026-06-18 10:31",
      warningCount: 3,
      metadata: {
        ...currentJob.metadata,
        language: "Русский",
        fieldCount: "14",
        confidence: "81%",
      },
    },
  ];

  window.Stage19ASampleData = {
    currentJob,
    jobs,
    infoPanels: {
      what:
        "DocuStruct AI помогает превратить изображения и PDF-документы в проверяемые поля, таблицы, предупреждения и Markdown.",
      pricing:
        "Цены пока не определены. Эта кнопка оставлена как навигационный placeholder для будущего продукта.",
      help:
        "Здесь позже появятся подсказки по форматам файлов, лимитам, статусам обработки и проверке результата.",
      privacy:
        "Текст о конфиденциальности не входит в текущий статический прототип.",
      terms: "Условия использования не входят в текущий статический прототип.",
      login:
        "Авторизация пока не подключена. Кнопка оставлена как placeholder для будущей рабочей области.",
    },
  };
})();
