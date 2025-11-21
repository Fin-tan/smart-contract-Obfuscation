# Smart Contract Obfuscation

Dự án này là một bản dựng lại (clone) của công cụ BiAn, tập trung vào việc làm rối mã nguồn Solidity theo từng bước tuần tự. Mục tiêu là khiến việc phân tích mã bị dịch ngược trở nên khó khăn hơn bằng cách biến đổi cả cú pháp lẫn luồng dữ liệu của hợp đồng thông minh.

## Kiến trúc chung

Toàn bộ logic chính được triển khai trong thư mục `BiAn-clone/`. Chương trình điều phối `demo.py` chạy lần lượt các mô-đun obfuscation, đồng thời sau mỗi bước nó:

1. Sinh lại AST mới thông qua `solc` và lưu vào `test/test_ast_stepN.json`.
2. Ghi snapshot Solidity tương ứng tại `test/test_stepN.sol` để tiện kiểm tra thủ công.

Trình tự pipeline hiện tại như sau:

| Bước | Mô-đun                  | Mô tả                                                                                                                                        |
| ---- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | Local State Promotion   | Đưa một số biến cục bộ đủ điều kiện thành biến trạng thái (state) để tăng phạm vi sống và độ phức tạp data flow.                             |
| 1    | Static Data Obfuscation | Thay literal (số, bool, string) bằng các lời gọi tra cứu động (`__get_*`).                                                                   |
| 2    | Boolean Obfuscation     | Biến đổi biểu thức logic thành dạng phức tạp hơn (ví dụ chuỗi toán học/bit xor).                                                             |
| 3    | Integer Obfuscation     | Làm nhiễu các biểu thức số học bằng các phép biến đổi tương đương (shift, xor, nhân/chia).                                                   |
| 4    | Scalar Splitting        | Bao gói các state scalar thành cặp hàm `__scalar_get`/`__scalar_set` với mảng noise 2 phần tử, khiến giá trị thực chỉ xuất hiện khi giải mã. |
| 5    | Comment Removal         | Loại bỏ chú thích còn sót lại.                                                                                                               |
| 6    | Format Scrambling       | Nén/thay đổi định dạng nguồn để khó đọc hơn.                                                                                                 |
| 7    | Variable Renaming       | Đổi tên biến/hàm sang chuỗi ngẫu nhiên nhằm phá vỡ ngữ nghĩa ban đầu.                                                                        |

Sau bước cuối, file kết quả ghi vào `test/test_output.sol` và AST cuối cùng nằm ở `test/test_ast.json`.

## Cách chạy thử

```powershell
cd BiAn-clone
python demo.py
```

Yêu cầu: đã cài đặt Python 3.10+ và bộ biên dịch `solc` 0.8.30 (script sẽ tự cài nếu cần).

Khi chạy, chương trình in log mỗi bước và đường dẫn tới các file snapshot. Mặc định, tệp `test/test_stepN.sol` được giữ lại để so sánh từng giai đoạn (có thể bật vệ sinh tự động bằng cách đặt biến môi trường `BIAN_CLEANUP_TEMPS=1`).

## Biến môi trường tùy chỉnh

Có thể bật/tắt từng mô-đun thông qua biến môi trường trước khi chạy `demo.py`:

- `BIAN_ENABLE_LOCAL_STATE` (mặc định `1`)
- `BIAN_ENABLE_STATIC`
- `BIAN_ENABLE_BOOLEAN`
- `BIAN_ENABLE_INTEGER`
- `BIAN_ENABLE_SCALAR`
- `BIAN_ENABLE_COMMENT_REMOVAL`
- `BIAN_ENABLE_LAYOUT` (điều khiển format scrambling)
- `BIAN_ENABLE_RENAMING`
- `BIAN_STATIC_ONLY` (`1` để chỉ chạy tới bước static data và bỏ qua các bước sau)
- `BIAN_CLEANUP_TEMPS` (`0` để giữ lại `test_step*.sol`, `1` để xóa sau khi chạy)

Ví dụ tắt hai bước cuối:

```powershell
setx BIAN_ENABLE_LAYOUT 0
setx BIAN_ENABLE_RENAMING 0
python demo.py
```

## Thư mục quan trọng

- `BiAn-clone/src/obfuscator/data-flow/` - chứa các mô-đun biến đổi data flow (`local_state_obfuscator.py`, `static_data_obfuscator.py`, `boolean_obfuscator.py`, `interger_obfuscator.py`, `scalar_splitter.py`).
- `BiAn-clone/src/obfuscator/layout/` - comment remover, thay đổi định dạng, đổi tên biến.
- `BiAn-clone/test/` - mẫu hợp đồng, kết quả từng bước, AST trung gian.

## Quy trình mở rộng

1. Viết mô-đun mới trong `src/obfuscator/...` với API nhận vào `source_text` và đường dẫn AST.
2. Chèn mô-đun vào pipeline trong `demo.py` đúng vị trí mong muốn và cập nhật log.
3. Giữ nguyên quy tắc: sau khi biến đổi phải sinh lại AST (`next_step`).
4. Thêm kiểm thử manual bằng cách xem `test_stepN.sol` để đảm bảo ngữ nghĩa vẫn đúng.

## Ghi chú triển khai

- Mọi thao tác thay thế dựa trên AST (dò offsets `src`) hoặc regex an toàn, nhằm hạn chế phá vỡ cú pháp.
- Scalar splitting chỉ áp dụng cho state variables `uint`/`uint256` không có initializer và visibility private/internal. Nếu biến cục bộ được chuyển thành state ở bước đầu (ví dụ `tmp` trong `compute`), nó cũng sẽ được split.
- Các helper (`__scalar_get`, `__scalar_set`) dùng XOR hai phần tử trong mảng noise để khôi phục giá trị thực, đồng thời giữ biến gốc bằng noise nhằm đánh lạc hướng khi đọc trực tiếp state.

## Hỗ trợ & đóng góp

- Kiểm tra diff ở `test/test_stepN.sol` để hiểu tác động mỗi mô-đun.