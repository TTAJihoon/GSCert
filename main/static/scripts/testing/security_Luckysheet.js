document.addEventListener("DOMContentLoaded", function () {
  luckysheet.create({
    container: "luckysheet",
    data: [{
      name: 'Sheet1',
      index: 'sheet1',
      status: 1,
      order: 0,
      row: 20,
      column: 10,
      celldata: [],
      config: {}
    }]
  });
});
