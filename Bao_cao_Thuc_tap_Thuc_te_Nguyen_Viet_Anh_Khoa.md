---
truong: Đại học Quốc tế Sài Gòn (SIU)
khoa: Khoa Khoa học Máy tính
nganh: Khoa học Máy tính
de_tai: Xây dựng hệ thống quản lý đội xe Fleet Fuel Management cho Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung
mssv: [[CẦN SỐ LIỆU: MSSV]]
sinh_vien: Nguyễn Việt Anh Khoa
gvhd: [[CẦN SỐ LIỆU: họ tên và học vị giảng viên hướng dẫn]]
don_vi: Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung (TT Ex-Trans)
thang: 08
nam: 2026
logo:
---

# LỜI CẢM ƠN

Em xin cảm ơn Khoa Khoa học Máy tính, Trường Đại học Quốc tế Sài Gòn đã tổ chức đợt thực tập thực tế và giới thiệu em đến Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung.

Em cảm ơn thầy/cô [[CẦN SỐ LIỆU: họ tên giảng viên hướng dẫn]], giảng viên hướng dẫn, đã góp ý về phạm vi đề tài và cách trình bày số liệu đo được trong báo cáo này.

Em cảm ơn anh/chị [[CẦN SỐ LIỆU: họ tên người hướng dẫn tại đơn vị, chức vụ]] tại Phòng Điều độ Vận tải đã dành thời gian giải thích quy trình chốt booking, quy định chụp hình giao nhận và cách bộ phận đang theo dõi nhiên liệu trên Excel. Phần lớn các ràng buộc nghiệp vụ được cài đặt trong hệ thống mô tả ở Chương 3 đến từ những buổi trao đổi đó.

Em cảm ơn các anh chị tài xế đã kiên nhẫn chụp và gửi lại ảnh giao nhận trong giai đoạn chạy thử phần mềm, khi giao diện còn nhiều lỗi.

Báo cáo này là kết quả làm việc trong một thời gian ngắn nên còn thiếu sót. Em mong nhận được nhận xét của thầy cô để chỉnh sửa.

# NHẬN XÉT CỦA ĐƠN VỊ THỰC TẬP

*(Trang này để trống. Đơn vị thực tập nhận xét, ký tên và đóng dấu.)*

# NHẬN XÉT CỦA GIẢNG VIÊN HƯỚNG DẪN

*(Trang này để trống. Giảng viên hướng dẫn nhận xét và ký tên.)*

# MỤC LỤC

*(Mục lục tự động. Trong Word, nhấn Ctrl+A rồi F9 để cập nhật số trang.)*

# DANH MỤC CÁC CHỮ VIẾT TẮT

| Chữ viết tắt | Nguyên văn | Nghĩa tiếng Việt |
|---|---|---|
| ACID | Atomicity, Consistency, Isolation, Durability | Bốn tính chất của giao dịch cơ sở dữ liệu |
| API | Application Programming Interface | Giao diện lập trình ứng dụng |
| ETA | Estimated Time of Arrival | Thời gian đến dự kiến |
| GPS | Global Positioning System | Hệ thống định vị toàn cầu |
| HGV | Heavy Goods Vehicle | Xe tải hạng nặng (hồ sơ định tuyến) |
| HTTP | HyperText Transfer Protocol | Giao thức truyền siêu văn bản |
| MTH | Mất tín hiệu | Trạng thái thiết bị định vị không liên lạc được (thuật ngữ của TTAS) |
| MVP | Minimum Viable Product | Sản phẩm khả dụng tối thiểu |
| ORM | Object-Relational Mapping | Ánh xạ đối tượng — quan hệ |
| ORS | OpenRouteService | Dịch vụ định tuyến đường bộ mã nguồn mở |
| PIP | Point-in-Polygon | Bài toán kiểm tra điểm nằm trong đa giác |
| REST | Representational State Transfer | Kiểu kiến trúc cho dịch vụ web |
| SQL | Structured Query Language | Ngôn ngữ truy vấn có cấu trúc |
| TLP | Truck Load Planner | Phân hệ xếp hàng lên thùng xe |
| TTAS | — | Nền tảng giám sát hành trình mà công ty đang thuê |
| VRP | Vehicle Routing Problem | Bài toán định tuyến phương tiện |
| WAL | Write-Ahead Logging | Chế độ ghi trước của SQLite |

# DANH MỤC HÌNH ẢNH, SƠ ĐỒ, BẢNG BIỂU

## Danh mục hình ảnh và sơ đồ

| Hình | Tên | Mục |
|---|---|---|
| Hình 1.1 | Quan hệ giữa VRP cổ điển, các biến thể có ràng buộc và phạm vi tự động hóa trong đề tài | 1.1.1 |
| Hình 2.1 | Sơ đồ tổ chức Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung | 2.3 |
| Hình 3.1 | Sơ đồ quy trình điều vận một ngày tại Phòng Điều độ Vận tải | 3.3.1 |
| Hình 3.2 | Kiến trúc ba tầng của hệ thống Fleet Fuel Management và các hệ thống ngoài | 3.3.2 |
| Hình C.1 | Bảng điều khiển điều độ | Phụ lục C |
| Hình C.2 | Trang hiệu suất nhiên liệu với các điểm bất thường | Phụ lục C |
| Hình C.3 | Trình dựng kế hoạch giao hàng, bước nhập từ Google Sheet | Phụ lục C |
| Hình C.4 | Trang bảo dưỡng theo chu kỳ km | Phụ lục C |
| Hình C.5 | Phương án xếp hàng trong thùng xe 2,5 tấn | Phụ lục C |
| Hình C.6 | Trình soạn vùng địa lý đa đa giác | Phụ lục C |
| Hình D.1 | Bảng tổng hợp booking hằng ngày | Phụ lục D |
| Hình D.2 | Biên bản sự cố chậm giao hàng | Phụ lục D |
| Hình D.3 | Nhật ký nhiên liệu trên Excel trước khi số hóa | Phụ lục D |

## Danh mục bảng biểu

| Bảng | Tên | Mục |
|---|---|---|
| Bảng 1.1 | So sánh phương pháp phát hiện bất thường tiêu hao nhiên liệu | 1.1.3 |
| Bảng 1.2 | Năm phân hệ của hệ thống và bài toán tương ứng | 1.2 |
| Bảng 1.3 | Mục tiêu kỳ vọng và trạng thái khi kết thúc đợt thực tập | 1.3 |
| Bảng 2.1 | Thông tin nhận dạng đơn vị thực tập | 2.1 |
| Bảng 2.2 | Chức năng các phòng ban và quan hệ với hệ thống được xây dựng | 2.3 |
| Bảng 2.3 | Phân bố điểm giao hàng theo tỉnh, thành | 2.4 |
| Bảng 2.4 | Cơ cấu đội xe do Thành Trung sở hữu | 2.5.2 |
| Bảng 2.5 | Sản lượng giao hàng ghi nhận trong hệ thống | 2.5.3 |
| Bảng 2.6 | Dữ liệu đổ nhiên liệu 23/6 – 28/7/2026 | 2.5.4 |
| Bảng 2.7 | Hiện trạng công cụ quản lý trước tháng 7/2026 | 2.6 |
| Bảng 3.1 | Các hạng mục công việc kỹ thuật theo mốc thời gian | 3.1 |
| Bảng 3.2 | Thành phần công nghệ | 3.3.2 |
| Bảng 3.3 | Phân bố tuyến đường theo blueprint | 3.3.2 |
| Bảng 3.4 | Ánh xạ chuỗi trạng thái của TTAS sang giá trị tốc độ | 3.3.3 |
| Bảng 3.5 | Trọng số hàm chấm điểm của phân hệ xếp hàng | 3.3.6 |
| Bảng 3.6 | Các dạng dữ liệu lệch chuẩn và cách xử lý | 3.3.7 |
| Bảng 3.7 | Hành vi của hệ thống khi từng hệ thống ngoài không khả dụng | 3.3.9 |
| Bảng 3.8 | Đại lượng đo được trên hệ thống tính đến 16/8/2026 | 3.4.1 |
| Bảng 3.9 | Kết quả chạy bộ kiểm thử ngày 16/8/2026 | 3.4.1 |
| Bảng 3.10 | Đo hiệu năng hai chế độ nhật ký của SQLite | 3.4.3 |
| Bảng 3.11 | Phân tích 323 phiếu đổ nhiên liệu | 3.5.2 |
| Bảng 3.12 | Phân tích 14 kế hoạch giao hàng | 3.5.3 |
| Bảng 3.13 | Tỷ lệ lỗi dữ liệu đo được trên các nguồn đầu vào | 3.5.4 |
| Bảng 4.1 | Kỹ năng chuyên môn được củng cố hoặc học mới | 4.2.1 |
| Bảng 4.2 | Môn học và điểm được vận dụng | 4.3.2 |

# MỞ ĐẦU

## 1. Lý do chọn đề tài

Chi phí logistics của Việt Nam hiện chiếm khoảng 16,5–18% GDP, so với mức trung bình toàn cầu khoảng 11,6%; Chiến lược phát triển dịch vụ logistics được Chính phủ phê duyệt đặt mục tiêu kéo con số này xuống 12–15% GDP vào năm 2035 [1]. Phần chênh lệch đó nằm ở khâu vận hành: xe chạy rỗng, chờ tại kho, tiêu hao nhiên liệu không được kiểm soát, và chứng từ giao nhận xử lý bằng tay.

<!-- nguồn: SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type — chạy trên routing_system.db ngày 2026-08-16 -->
Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung (thương hiệu vận tải TT Ex-Trans) tự sở hữu và vận hành 36 phương tiện: 32 xe tải thùng kín từ 1,5 đến 10 tấn và 4 xe đầu kéo container. Sản lượng vượt quá năng lực đội xe nhà được chuyển cho các nhà xe liên kết. Ở quy mô này, mọi con số vận hành đều đang được ghi trên Excel và Zalo — đủ nhỏ để không sập, nhưng đủ lớn để không ai kiểm tra lại được.

Đề tài được chọn vì ba lý do cụ thể. Thứ nhất, dữ liệu vận hành ở đây là dữ liệu thật, chưa qua làm sạch: tọa độ GPS trôi khi xe đứng yên, biển số cùng một xe được ghi ba kiểu khác nhau, cột ngày trong bảng kế hoạch là chữ chứ không phải kiểu ngày tháng. Đây là loại dữ liệu mà bài tập trên lớp không có. Thứ hai, các bài toán ở đây ánh xạ trực tiếp sang những gì em đã học: kiểm tra điểm trong đa giác cho hàng rào địa lý, bài toán định tuyến phương tiện cho việc xếp lộ trình, xếp hộp ba chiều cho việc xếp hàng lên thùng xe. Thứ ba, kết quả có thể đo được — số lần đổ nhiên liệu bị gắn cờ bất thường, số ảnh giao nhận được lưu vào cơ sở dữ liệu thay vì Zalo, số trường hợp kiểm thử tự động chạy qua.

## 2. Mục tiêu nghiên cứu thực tập thực tế

Đợt thực tập đặt ra bốn mục tiêu:

1. Ghi lại quy trình điều vận thực tế tại Phòng Điều độ Vận tải dưới dạng sơ đồ luồng, gồm cả các bước không thuộc chuyên môn công nghệ thông tin.
2. Xác định các điểm nghẽn dữ liệu trong quy trình đó và diễn đạt lại chúng thành bài toán kỹ thuật có thể lập trình được.
3. Xây dựng và triển khai một hệ thống phần mềm chạy được trên môi trường thật, giải quyết ít nhất ba trong số các điểm nghẽn đã xác định.
4. Kiểm chứng hệ thống bằng bộ kiểm thử tự động và bằng dữ liệu vận hành thật, không dựa vào đánh giá cảm tính.

## 3. Phương pháp, đối tượng và phạm vi nghiên cứu

**Đối tượng.** Quy trình điều vận và giao nhận của đội 36 xe do Thành Trung sở hữu, cùng dữ liệu hành trình, dữ liệu đổ nhiên liệu và dữ liệu giao hàng phát sinh từ đội xe này.

**Phạm vi.** Báo cáo giới hạn ở luồng thông tin từ khi Phòng Kinh doanh chốt booking đến khi tài xế hoàn tất giao hàng và nộp chứng từ. Phần định giá cước, kế toán công nợ và thủ tục hải quan nằm ngoài phạm vi. Về mặt kỹ thuật, hệ thống chỉ đọc dữ liệu định vị từ nền tảng TTAS mà công ty đang thuê, không can thiệp vào thiết bị đầu cuối trên xe.

**Phương pháp.**

| Phương pháp | Cách thực hiện | Dùng cho mục nào |
|---|---|---|
| Quan sát tại chỗ | Ngồi tại Phòng Điều độ trong các ca chốt booking buổi chiều | 3.1, 3.3 |
| Phỏng vấn bán cấu trúc | Trao đổi với nhân sự Điều độ, Kỹ thuật — Vật tư, Kinh doanh | 2.3, 3.1, 3.2 |
| Phân tích dữ liệu hiện có | Đọc bảng Excel nhiên liệu và bảng kế hoạch Google Sheet của quản lý | 3.2, 3.5 |
| Phát triển phần mềm lặp | Mỗi vòng: cài đặt — cho bộ phận dùng thử — sửa theo phản hồi | 3.3, 3.4 |
| Kiểm thử tự động | Viết test cho từng tầng, chạy lại toàn bộ sau mỗi thay đổi | 3.4, 3.5 |
| Đo trên hệ thống thật | Truy vấn cơ sở dữ liệu sản xuất, đo thời gian phản hồi | 3.5 |

## 4. Nội dung nghiên cứu thực tập thực tế

Chương 1 trình bày các kiến thức đã học được dùng lại trong đề tài: bài toán định tuyến phương tiện, thuật toán kiểm tra điểm trong đa giác, phát hiện bất thường bằng trung bình trượt, bài toán xếp hộp ba chiều và các nguyên tắc thiết kế cơ sở dữ liệu quan hệ. Chương 2 mô tả Công ty Thành Trung: cơ cấu tổ chức, ngành nghề, quy mô nhân sự và năng lực đội xe. Chương 3 là phần chính — công việc được giao, các bài toán phải giải, quy trình và phương pháp thực hiện, kết quả đo được và phần chưa làm được. Chương 4 là phần tự đánh giá. Phần Kết luận tóm tắt và nêu bốn kiến nghị cho công ty.

# CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN

## 1.1. Tổng quan cơ sở lý thuyết

Mục này chỉ trình bày những kiến thức đã học ở trường mà em đã dùng lại trong đề tài. Mỗi tiểu mục nêu bài toán, thuật toán, độ phức tạp, và chỉ ra chỗ nó được cài đặt trong hệ thống mô tả ở Chương 3.

### 1.1.1. Bài toán định tuyến phương tiện

Bài toán định tuyến phương tiện (Vehicle Routing Problem — VRP) được Dantzig và Ramser đặt ra năm 1959 với đúng tình huống của một doanh nghiệp vận tải: một đội xe xuất phát từ một kho trung tâm phải phục vụ một tập điểm giao hàng sao cho tổng quãng đường là nhỏ nhất [2]. Bài toán gốc trong [2] là giao xăng từ tổng kho tới các cây xăng — cùng loại bài toán mà Phòng Điều độ giải bằng tay mỗi chiều.

VRP là bài toán NP-khó: không gian lời giải tăng theo giai thừa của số điểm dừng, nên với số điểm dừng cỡ vài chục đã không thể duyệt hết. Toth và Vigo phân loại các biến thể thực tế và các họ thuật toán giải chúng: thuật toán chính xác dựa trên quy hoạch nguyên, thuật toán heuristic dựng lời giải, và metaheuristic cải thiện lời giải [3]. Trong thực tế vận tải hàng hóa, bài toán còn kèm các ràng buộc mà VRP cổ điển không có: sức chở của từng xe (Capacitated VRP), khung giờ giao hàng của khách (VRP with Time Windows), và giới hạn hạ tầng theo loại phương tiện.

Trong phạm vi đề tài này, em **không** cài đặt một bộ giải VRP. Số điểm dừng mỗi xe mỗi ngày ở Thành Trung nằm trong khoảng vài điểm, và thứ tự dừng do điều độ viên quyết định theo các ràng buộc không có trong dữ liệu (quan hệ với khách, giờ mở cửa kho, tình trạng tài xế). Phần được tự động hóa là bước con của VRP: tính ma trận khoảng cách và thời gian di chuyển giữa các điểm theo hồ sơ xe tải nặng, để điều độ viên có số liệu khi tự sắp thứ tự. Lý do lựa chọn này được phân tích ở mục 3.4.3.

![Hình 1.1. Quan hệ giữa VRP cổ điển, các biến thể có ràng buộc và phạm vi tự động hóa trong đề tài](placeholder)

### 1.1.2. Kiểm tra điểm nằm trong đa giác và hàng rào địa lý

Hàng rào địa lý (geofence) là một vùng ảo vẽ trên bản đồ; hệ thống phát sinh sự kiện khi phương tiện đi vào hoặc rời khỏi vùng đó. Reclus và Drouard mô tả kỹ thuật này cùng các ứng dụng trong quản lý đội xe và vận tải hàng hóa: giám sát từ xa mà không cần con người báo cáo [4].

Về mặt tính toán, geofence quy về bài toán điểm trong đa giác (Point-in-Polygon). Hormann và Agathos trình bày hai nhóm lời giải: quy tắc chẵn — lẻ, dẫn tới các thuật toán đếm giao điểm của tia (ray crossing), và số vòng quấn (winding number), dẫn tới các thuật toán cộng góc [5].

Thuật toán ray casting theo quy tắc chẵn — lẻ hoạt động như sau: từ điểm cần kiểm tra, phóng một tia theo phương ngang ra vô cực, đếm số lần tia cắt các cạnh của đa giác. Số lần cắt lẻ thì điểm nằm trong, chẵn thì nằm ngoài. Với đa giác n đỉnh, thuật toán duyệt từng cạnh một lần nên độ phức tạp là O(n), bộ nhớ O(1). Đây là lý do nó chạy được ở tần suất mỗi 60 giây cho toàn đội xe mà không cần cấu trúc dữ liệu không gian phụ trợ.

Hormann và Agathos chỉ ra các trường hợp biên phải xử lý riêng: điểm nằm đúng trên cạnh, tia đi qua đúng một đỉnh (bị đếm hai lần), và đa giác tự cắt [5]. Chi tiết cài đặt và cách xử lý các trường hợp này được nêu ở mục 3.3.4.

Khi vùng cần mô tả gồm nhiều mảnh rời (một kho có hai cổng vào ở hai phía), cần đa đa giác (multi-polygon) và một điểm đại diện cho cả cụm. Trọng tâm của đa giác phẳng tính bằng công thức trọng tâm có trọng số diện tích, và trọng tâm của đa đa giác là trung bình các trọng tâm thành phần có trọng số là diện tích từng mảnh — kiến thức hình học tính toán trong môn Cấu trúc dữ liệu và Giải thuật.

Khoảng cách giữa hai điểm trên mặt cầu tính bằng công thức haversine [6], với bán kính Trái Đất quy ước 6 371 000 m. Công thức haversine được chọn thay cho định luật cosin cầu vì nó ổn định số học ở khoảng cách nhỏ — đúng vùng giá trị mà bài toán geofence làm việc (hàng chục đến hàng trăm mét) [6].

### 1.1.3. Phát hiện bất thường bằng trung bình trượt

Chandola, Banerjee và Kumar định nghĩa phát hiện bất thường là việc tìm các mẫu dữ liệu không tuân theo hành vi được coi là bình thường, và phân loại các kỹ thuật theo cách chúng định nghĩa "bình thường": dựa trên phân loại, dựa trên láng giềng gần nhất, dựa trên phân cụm, dựa trên thống kê, và dựa trên lý thuyết thông tin [7]. Bài khảo sát cũng nêu rõ ba dạng bài toán: có nhãn đầy đủ, có nhãn một phần, và không có nhãn.

Bài toán nhiên liệu ở Thành Trung thuộc dạng **không có nhãn**: không có tập phiếu đổ nào được đánh dấu sẵn là "gian lận" hay "bình thường". Đây là ràng buộc quyết định lựa chọn phương pháp — không thể huấn luyện mô hình phân loại có giám sát khi không có nhãn.

Phương pháp được chọn thuộc nhóm thống kê: dựng một đường cơ sở (baseline) cho từng phương tiện từ chính lịch sử của nó, rồi gắn cờ khi giá trị mới vượt baseline quá một hệ số. Trung bình trượt là dạng đơn giản nhất của họ phương pháp này. Roberts đã hình thức hóa biểu đồ kiểm soát dựa trên trung bình trượt hình học từ năm 1959, trong đó quan sát gần nhất được gán trọng số lớn hơn và so sánh với các biểu đồ dùng trung bình trượt thông thường [8].

Barbado và Corcho áp dụng đúng bài toán này trên dữ liệu telematics của các đội xe công nghiệp, kết hợp phát hiện bất thường không giám sát với mô hình học máy diễn giải được để chỉ ra nguyên nhân của mức tiêu hao bất thường [9]. Điểm em rút ra từ [9] không phải là mô hình, mà là yêu cầu về khả năng diễn giải: một cảnh báo mà bộ phận Kỹ thuật không hiểu vì sao lại bật thì sẽ bị bỏ qua. Trung bình trượt trên 5 phiếu gần nhất thỏa mãn yêu cầu này — nhân viên có thể tự kiểm lại bằng máy tính bỏ túi.

Bảng 1.1 so sánh các lựa chọn đã cân nhắc.

**Bảng 1.1. So sánh phương pháp phát hiện bất thường tiêu hao nhiên liệu**

| Phương pháp | Cần nhãn | Diễn giải được | Dữ liệu tối thiểu | Quyết định |
|---|---|---|---|---|
| Phân loại có giám sát | Có | Trung bình | Vài trăm mẫu có nhãn | Loại — không có nhãn |
| Isolation Forest | Không | Thấp | Vài trăm mẫu | Loại — khó giải thích cho bộ phận Kỹ thuật |
| Phân rã chuỗi thời gian theo mùa | Không | Trung bình | Vài chu kỳ đầy đủ | Loại — chuỗi mỗi xe quá ngắn |
| Trung bình trượt + ngưỡng nhân | Không | Cao | 5 phiếu/xe | **Chọn** |

<!-- nguồn: bảng do sinh viên tự lập, cột "Quyết định" phản ánh lựa chọn đã cài đặt trong app/routes/fuel.py::_compute_baseline -->

### 1.1.4. Bài toán xếp hộp ba chiều

Xếp hàng lên thùng xe là bài toán xếp hộp ba chiều (3D bin packing / container loading), cũng thuộc lớp NP-khó. Bortfeldt và Wäscher khảo sát các ràng buộc xuất hiện trong thực tế mà phần lớn nghiên cứu trước đó bỏ qua, và chia chúng thành các nhóm: ràng buộc về thùng chứa, về hàng hóa, về xếp chồng, về phân bố tải trọng và về khả năng dỡ hàng theo thứ tự [10].

Ba nhóm ràng buộc trong [10] xuất hiện trực tiếp trong đề tài:

- **Ràng buộc đỡ đáy (supporting constraint):** một kiện chỉ được đặt lên khi diện tích mặt đáy được đỡ đủ, nếu không nó sẽ đổ khi xe phanh.
- **Ràng buộc phân bố tải trọng:** trọng tâm khối hàng phải nằm trong vùng cho phép so với trục xe.
- **Ràng buộc thứ tự dỡ hàng (multi-drop):** kiện của điểm giao đầu tiên phải nằm gần cửa.

Bài toán được tiếp cận bằng heuristic dựng lời giải theo điểm ứng viên: duy trì tập vị trí khả dĩ, với mỗi kiện thử đặt vào từng vị trí và từng hướng xoay, chấm điểm và giữ vị trí điểm cao nhất. Hàm chấm điểm là nơi các ràng buộc thực tế được mã hóa thành số. Cấu hình trọng số cụ thể được trình bày ở mục 3.3.6.

### 1.1.5. Mô hình quan hệ và thiết kế cơ sở dữ liệu

Codd đề xuất mô hình quan hệ năm 1970 để tách biểu diễn logic của dữ liệu khỏi cách lưu trữ vật lý [11]. Các kiến thức từ môn Cơ sở dữ liệu được dùng lại trong đề tài gồm: khóa chính và khóa ngoại, ràng buộc UNIQUE, chuẩn hóa để loại bỏ dư thừa, chỉ mục để tăng tốc truy vấn, và tính chất ACID của giao dịch.

Hai điểm được vận dụng có ý thức trong thiết kế lược đồ ở mục 3.3.2:

- **Ràng buộc UNIQUE thay cho kiểm tra ở tầng ứng dụng.** Bảng nhật ký số km bảo dưỡng đặt UNIQUE trên cặp (biển số, ngày ghi nhận). Khi tiến trình đồng bộ chạy lại trong cùng một ngày, cơ sở dữ liệu từ chối bản ghi trùng thay vì để ứng dụng phải nhớ kiểm tra.
- **Phạm vi giao dịch.** Một giao dịch ghi giữ khóa ghi trên toàn tệp cơ sở dữ liệu cho tới khi commit. Sai lầm về phạm vi giao dịch trong đề tài này đã gây ra một lỗi thật, được phân tích ở mục 3.4.3.

### 1.1.6. Kiến trúc ứng dụng web và REST

Fielding định nghĩa REST như một kiểu kiến trúc cho hệ thống phân tán trên mạng, với các ràng buộc: giao diện thống nhất, phi trạng thái, phân tầng, và có thể lưu đệm [12]. Hệ thống trong đề tài áp dụng ràng buộc phi trạng thái cho tầng API: mỗi yêu cầu HTTP mang đủ thông tin để xử lý, không có phiên phía máy chủ.

Ràng buộc lưu đệm được áp dụng ở chỗ dữ liệu định vị: dữ liệu GPS được tiến trình nền làm mới theo chu kỳ và giữ trong bộ nhớ tiến trình, các yêu cầu đọc lấy từ đó thay vì gọi thẳng sang TTAS. Hệ quả kiến trúc của lựa chọn này — bộ nhớ đệm nằm trong tiến trình nên không chia sẻ được giữa nhiều tiến trình xử lý — được phân tích ở mục 3.4.3.

## 1.2. Chủ đề thực tập

Chủ đề là xây dựng **Fleet Fuel Management** — hệ thống quản lý đội xe cho Công ty Thành Trung, gồm năm phân hệ:

**Bảng 1.2. Năm phân hệ của hệ thống và bài toán tương ứng**

| Phân hệ | Bài toán nghiệp vụ | Cơ sở lý thuyết |
|---|---|---|
| Theo dõi hành trình | Điều độ không biết xe đang ở đâu | 1.1.2 — geofence, haversine |
| Định tuyến | Không có ETA đáng tin cho từng loại xe | 1.1.1 — VRP, ma trận khoảng cách |
| Giám sát nhiên liệu | Hao hụt phát hiện muộn hoặc không phát hiện | 1.1.3 — trung bình trượt |
| Nhắc bảo dưỡng | Lịch thay nhớt theo dõi bằng tay trên Excel | 1.1.5 — ràng buộc UNIQUE, đồng bộ |
| Kế hoạch giao hàng | Chứng từ và ảnh giao nhận nằm rải trên Zalo | 1.1.5, 1.1.6 — lược đồ quan hệ, REST |

Tên hệ thống được giữ nguyên là **Fleet Fuel Management** trong toàn bộ báo cáo, kể cả ở các phân hệ không liên quan tới nhiên liệu — đây là tên trong mã nguồn và trong cách gọi của bộ phận Điều độ.

## 1.3. Các kết quả, mục tiêu kỳ vọng

Trước khi bắt đầu, các mục tiêu sau được thống nhất với người hướng dẫn tại đơn vị:

**Bảng 1.3. Mục tiêu kỳ vọng và trạng thái khi kết thúc đợt thực tập**

| # | Mục tiêu đặt ra ban đầu | Trạng thái | Đối chiếu |
|---|---|---|---|
| 1 | Hệ thống chạy được trên máy chủ thật, bộ phận truy cập qua trình duyệt | Đạt | 3.4.1 |
| 2 | Tự động lấy dữ liệu định vị từ TTAS, không nhập tay | Đạt | 3.3.3 |
| 3 | Tự động phát hiện xe vào/ra kho bằng geofence | Đạt một phần | 3.4.3 |
| 4 | Gắn cờ tự động các phiếu đổ nhiên liệu bất thường | Đạt | 3.4.1, 3.5.2 |
| 5 | Số hóa ảnh giao nhận thay cho Zalo | Đạt | 3.5.3 |
| 6 | Nhắc bảo dưỡng tự động theo số km | Đạt một phần | 3.4.3 |
| 7 | Hỗ trợ xếp hàng lên thùng xe | Đạt một phần | 3.3.6, 3.4.3 |

Mục tiêu ban đầu còn có một chỉ tiêu "giảm 80% thao tác ghi chép thủ công". Chỉ tiêu này **không được dùng làm kết quả trong báo cáo**: khối lượng thao tác thủ công trước khi triển khai chưa từng được đo, nên không có mốc để so sánh. Mục 3.5 chỉ trình bày những đại lượng đo được cả trước lẫn sau, hoặc chỉ đo được sau và được ghi rõ là như vậy.

# CHƯƠNG 2: MÔ TẢ CƠ QUAN THỰC TẬP THỰC TẾ

## 2.1. Thông tin cơ quan

**Bảng 2.1. Thông tin nhận dạng đơn vị thực tập**

| Hạng mục | Nội dung |
|---|---|
| Tên đầy đủ | Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung |
| Thương hiệu vận tải | TT Ex-Trans |
| Lĩnh vực | Vận tải hàng hóa đường bộ, giao nhận, dịch vụ logistics |
| Mã số doanh nghiệp | [[CẦN SỐ LIỆU: mã số thuế / MSDN, lấy từ giấy chứng nhận đăng ký doanh nghiệp]] |
| Năm thành lập | [[CẦN SỐ LIỆU: năm thành lập theo giấy phép]] |
| Vốn điều lệ | [[CẦN SỐ LIỆU: vốn điều lệ theo đăng ký kinh doanh]] |
| Trụ sở chính | [[CẦN SỐ LIỆU: địa chỉ trụ sở theo đăng ký]] |
| Người đại diện pháp luật | [[CẦN SỐ LIỆU: họ tên, chức vụ]] |
| Website / liên hệ | [[CẦN SỐ LIỆU]] |

<!-- Các ô [[CẦN SỐ LIỆU]] ở trên phải lấy từ giấy đăng ký kinh doanh hoặc hồ sơ năng lực do phòng Hành chính cung cấp. Không tra trên website bên thứ ba rồi ghi vào báo cáo. -->

Địa bàn khai thác của công ty được xác định từ dữ liệu vận hành thật chứ không từ hồ sơ giới thiệu. Toàn bộ 243 điểm dừng trong 14 kế hoạch giao hàng từ ngày 01/8 đến 16/8/2026 nằm trong khoảng vĩ độ 8,966–10,903 và kinh độ 104,558–106,690, tức toàn bộ vùng Đồng bằng sông Cửu Long và rìa Đông Nam Bộ.

<!-- nguồn: SELECT ROUND(MIN(lat),3),ROUND(MAX(lat),3),ROUND(MIN(lng),3),ROUND(MAX(lng),3) FROM delivery_plan_stops WHERE lat IS NOT NULL — chạy 2026-08-16 -->

Biển số của cả 36 phương tiện thuộc các sê-ri 50E, 50F, 50H, 51C, 51D — đều là biển đăng ký tại Thành phố Hồ Chí Minh, xác nhận đầu mối vận hành đặt tại TP.HCM và tuyến khai thác chính là TP.HCM đi các tỉnh miền Tây.

<!-- nguồn: SELECT plate_number FROM vehicles ORDER BY plate_number — chạy 2026-08-16, 36 dòng -->

## 2.2. Lịch sử hình thành và phát triển

[[CẦN SỐ LIỆU: mốc thành lập, các mốc mở rộng đội xe, mốc ký hợp đồng với khách hàng lớn — lấy từ hồ sơ năng lực công ty hoặc phỏng vấn ban giám đốc. Không suy đoán từ website.]]

Phần lịch sử có thể ghi nhận trực tiếp trong đợt thực tập là mốc chuyển đổi công cụ quản lý. Trước tháng 7/2026, toàn bộ dữ liệu nhiên liệu, số km bảo dưỡng và chứng từ giao nhận được quản lý bằng Excel và Zalo. Từ 09/7/2026, hệ thống Fleet Fuel Management bắt đầu được xây dựng; kế hoạch giao hàng đầu tiên được nhập vào hệ thống ngày 01/8/2026 và từ đó chạy liên tục.

<!-- nguồn: git log --reverse --format='%ad %s' --date=short → commit đầu 2026-07-09; SELECT MIN(plan_date) FROM delivery_plans → 2026-08-01 -->

## 2.3. Cơ cấu tổ chức, nhiệm vụ chức năng của các phòng ban

![Hình 2.1. Sơ đồ tổ chức Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung](placeholder)

Công ty tổ chức theo mô hình trực tuyến — chức năng. Ban Giám đốc điều hành trực tiếp các phòng chuyên môn; luồng công việc chính đi qua ba phòng theo thứ tự Kinh doanh → Điều độ Vận tải → Kỹ thuật — Vật tư.

**Bảng 2.2. Chức năng các phòng ban và quan hệ với hệ thống được xây dựng**

| Phòng ban | Nhiệm vụ chính | Dữ liệu tạo ra | Phân hệ liên quan |
|---|---|---|---|
| Ban Giám đốc | Quyết định đầu tư phương tiện, phê duyệt hợp đồng | — | — |
| Phòng Kinh doanh | Nhận booking, báo giá, chăm sóc khách hàng, theo dõi công nợ | Bảng tổng hợp booking hằng ngày | Kế hoạch giao hàng |
| Phòng Điều độ Vận tải | Xếp xe — tài xế — tuyến, theo dõi hành trình, xử lý sự cố | Kế hoạch giao hàng, biên bản sự cố | Toàn bộ 5 phân hệ |
| Phòng Kỹ thuật — Vật tư | Bảo dưỡng, sửa chữa, quản lý phụ tùng, định mức nhiên liệu | Phiếu đổ nhiên liệu, lịch thay nhớt | Nhiên liệu, bảo dưỡng |
| Phòng Kế toán — Tài chính | Thanh toán, quyết toán chi phí nhiên liệu, lương tài xế | Chứng từ thanh toán | Xuất báo cáo cuối ngày |
| Phòng Nhân sự — Hành chính | Tuyển dụng, hợp đồng lao động tài xế, giấy tờ phương tiện | Hồ sơ tài xế | Danh mục tài xế |

Phòng Điều độ Vận tải là bộ phận em tham gia. Đây cũng là nút giao của toàn bộ luồng thông tin: mọi liên lạc giữa tài xế và khách hàng đều phải đi qua phòng này, theo quy định vận hành nội bộ [13]. Quy định này có hệ quả kỹ thuật trực tiếp — nó biến Phòng Điều độ thành nguồn dữ liệu duy nhất về trạng thái chuyến hàng, và vì vậy cũng thành điểm nghẽn khi nhân sự phòng bận (phân tích ở mục 3.2.1).

[[CẦN SỐ LIỆU: số nhân sự từng phòng ban, để bổ sung một cột vào Bảng 2.2 — lấy từ phòng Nhân sự]]

## 2.4. Chức năng, nhiệm vụ, phạm vi ngành nghề hoạt động

Công ty khai thác ba nhóm dịch vụ:

**Vận tải hàng hóa chặng dài liên tỉnh.** Tuyến chính là TP.HCM đi các tỉnh Đồng bằng sông Cửu Long. Trong 243 điểm dừng thuộc 14 kế hoạch giao hàng tháng 8/2026, phân bố theo tỉnh như sau.

**Bảng 2.3. Phân bố điểm giao hàng theo tỉnh, thành (kế hoạch 01/8 – 16/8/2026)**

<!-- nguồn: phân tách cột address của delivery_plan_stops theo dấu phẩy cuối, đếm bằng Python — chạy 2026-08-16. 45/243 dòng có địa chỉ không ghi tỉnh ở cuối chuỗi nên không phân loại được. -->

| Tỉnh, thành | Số điểm dừng |
|---|---|
| Cần Thơ | 89 |
| An Giang | 35 |
| Đồng Tháp | 30 |
| Vĩnh Long | 27 |
| Cà Mau | 10 |
| Hậu Giang | 1 |
| Bạc Liêu | 1 |
| Trà Vinh | 1 |
| Không phân loại được từ chuỗi địa chỉ | 49 |
| **Tổng** | **243** |

Mã điểm giao hàng do khách hàng đặt cũng cho thấy vùng phủ rộng hơn con số địa chỉ phân loại được: tiền tố mã trạm gồm CT (Cần Thơ, 65 lần), DT (Đồng Tháp, 39), AG (An Giang, 26), BT (Bến Tre, 24), HG (Hậu Giang, 21), BL (Bạc Liêu, 16), ST (Sóc Trăng, 16), TV (Trà Vinh, 13), KG (Kiên Giang, 9), VL (Vĩnh Long, 7), TG (Tiền Giang, 3), CM (Cà Mau, 3). Tổng cộng 12 tỉnh, thành miền Tây.

<!-- nguồn: đếm tiền tố 2 ký tự của station_name trong delivery_plan_stops — chạy 2026-08-16 -->

**Vận tải chặng ngắn và phân phối.** Giao hàng trong nội thành TP.HCM và các tỉnh giáp ranh bằng xe tải thùng kín tải trọng nhỏ.

**Giao nhận xuất nhập khẩu.** Kéo container từ cảng về kho khách hàng và ngược lại, bằng 4 đầu kéo của công ty.

## 2.5. Quy mô nhân sự, năng lực sản xuất, kinh doanh, dịch vụ

### 2.5.1. Nhân sự

[[CẦN SỐ LIỆU: tổng số nhân sự, số tài xế, số nhân viên văn phòng — lấy từ phòng Nhân sự. Bản nháp trước đó ghi "gần 150 nhân sự" nhưng con số này không kiểm chứng được nên đã bỏ.]]

Số tài xế được định danh trong cơ sở dữ liệu hệ thống hiện là 2. Con số này **không phải** số tài xế của công ty: hệ thống chỉ tạo bản ghi tài xế khi tên được xác nhận, còn tên tài xế nhập từ bảng kế hoạch của quản lý được lưu vào trường ghi đè `driver_name_override` do có lỗi chính tả và có dòng ghi nhầm ghi chú vào ô tên. Lý do thiết kế như vậy nêu ở mục 3.3.5.

<!-- nguồn: SELECT COUNT(*) FROM drivers → 2; đọc docstring services/delivery/sheet_import_service.py -->

### 2.5.2. Năng lực đội xe

Công ty tự sở hữu 36 phương tiện. Phần sản lượng vượt năng lực đội xe nhà được chuyển cho các nhà xe liên kết; các xe này không thuộc phạm vi hệ thống và không có trong cơ sở dữ liệu.

**Bảng 2.4. Cơ cấu đội xe do Thành Trung sở hữu**

<!-- nguồn: SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type — chạy trên routing_system.db ngày 2026-08-16 -->

| Loại phương tiện | Số lượng | Tỷ lệ |
|---|---|---|
| Xe tải 2,5 tấn | 15 | 41,7% |
| Xe tải 5 tấn | 5 | 13,9% |
| Xe tải 10 tấn | 4 | 11,1% |
| Xe tải 1,5 tấn | 4 | 11,1% |
| Đầu kéo container | 4 | 11,1% |
| Xe tải 9 tấn | 2 | 5,6% |
| Xe tải 8 tấn | 2 | 5,6% |
| **Tổng** | **36** | **100%** |

Cơ cấu này giải thích một quyết định thiết kế ở mục 3.3.6: xe 2,5 tấn chiếm 41,7% đội xe, nên cấu hình thùng của loại xe này là cấu hình được tối ưu trước tiên trong phân hệ xếp hàng.

[[CẦN SỐ LIỆU: số rơ moóc, số xe của các nhà xe liên kết thường xuyên — lấy từ phòng Điều độ]]

### 2.5.3. Sản lượng khai thác đo được

Bảng 2.5 tổng hợp sản lượng thực tế đo từ cơ sở dữ liệu hệ thống. Đây là dữ liệu của riêng khách hàng có kế hoạch được nhập vào hệ thống, không phải toàn bộ sản lượng công ty.

**Bảng 2.5. Sản lượng giao hàng ghi nhận trong hệ thống, 01/8 – 16/8/2026**

<!-- nguồn: các truy vấn trên routing_system.db chạy 2026-08-16, ghi trong Phụ lục A -->

| Chỉ tiêu | Giá trị |
|---|---|
| Số ngày có kế hoạch | 14 |
| Tổng lượt xe được phân công | 62 |
| Số xe phân công trung bình mỗi ngày | 4,4 (thấp nhất 3, cao nhất 6) |
| Tổng điểm dừng theo kế hoạch | 243 |
| Điểm dừng trung bình mỗi xe mỗi ngày | 3,9 (thấp nhất 2, cao nhất 5) |
| Điểm dừng nhiều nhất trong một ngày | 24 (ngày 12/8/2026) |
| Số điểm giao hàng riêng biệt | 241 |
| Điểm dừng đã hoàn tất | 224 |
| Điểm dừng bị hủy | 2 |
| Điểm dừng còn ở trạng thái kế hoạch | 17 |

Tỷ lệ hoàn tất trên các điểm đã đến hạn là 224/226, tức 99,1%. Hai điểm bị hủy đều có lý do hủy được ghi lại trong hệ thống.

### 2.5.4. Sản lượng nhiên liệu đo được

**Bảng 2.6. Dữ liệu đổ nhiên liệu, 23/6 – 28/7/2026**

<!-- nguồn: SELECT COUNT(*), MIN(log_date), MAX(log_date) FROM fuel_log; SELECT ROUND(SUM(liters),1), ROUND(SUM(liters*unit_price)) FROM fuel_log WHERE unit_price IS NOT NULL — chạy 2026-08-16 -->

| Chỉ tiêu | Giá trị |
|---|---|
| Số phiếu đổ | 323 |
| Khoảng thời gian | 23/6/2026 – 28/7/2026 (36 ngày) |
| Số phương tiện có phát sinh | 31 |
| Tổng lượng nhiên liệu | 19 967,2 lít |
| Tổng chi phí | 452 679 427 VND |
| Số phiếu tính được mức tiêu hao (có đủ km cũ và km mới) | 319 |
| Số phiếu không tính được mức tiêu hao | 4 |

Trung bình mỗi ngày phát sinh 9 phiếu đổ, tương ứng khoảng 555 lít và 12,6 triệu đồng chi phí nhiên liệu. Trước khi có hệ thống, toàn bộ 323 phiếu này được nhập tay vào Excel và không có cơ chế kiểm tra chéo nào.

## 2.6. Nội dung khác: hạ tầng công nghệ thông tin hiện có

Khảo sát hạ tầng công nghệ trước khi triển khai cho kết quả ở Bảng 2.7. Đây là điểm xuất phát của toàn bộ công việc ở Chương 3.

**Bảng 2.7. Hiện trạng công cụ quản lý trước tháng 7/2026**

| Nghiệp vụ | Công cụ đang dùng | Hạn chế quan sát được |
|---|---|---|
| Định vị phương tiện | Nền tảng TTAS thuê ngoài, giao diện web | Không có API công khai, phải mở trình duyệt xem từng xe |
| Kế hoạch giao hàng | Google Sheet do quản lý tự nhập | Cột ngày và cột tọa độ là chữ, nhiều định dạng lẫn lộn |
| Chứng từ, ảnh giao nhận | Nhóm Zalo | Ảnh trôi theo dòng tin, không tra cứu được theo chuyến |
| Nhật ký nhiên liệu | Excel, Google Sheet | Không có kiểm tra bất thường, nhập tay |
| Lịch bảo dưỡng | Excel | Số km cập nhật thủ công, dễ bỏ sót |
| Xếp hàng lên xe | Kinh nghiệm tài xế và điều độ viên | Không có bản vẽ, không kiểm tra được tải trọng trục |

Đặc điểm chung: mỗi nghiệp vụ có một công cụ riêng, không công cụ nào nói chuyện được với công cụ nào, và không công cụ nào lưu vết đủ để truy lại một chuyến hàng đã xong. Chương 3 trình bày cách xử lý.

# CHƯƠNG 3: NỘI DUNG THỰC TẬP THỰC TẾ

## 3.1. Mô tả công việc được giao

Em được phân về Phòng Điều độ Vận tải, thời gian thực tập [[CẦN SỐ LIỆU: ngày bắt đầu – ngày kết thúc theo giấy giới thiệu]], người hướng dẫn tại đơn vị là [[CẦN SỐ LIỆU: họ tên, chức vụ]].

Công việc được giao chia làm hai phần. Phần thứ nhất là công việc của phòng, không thuộc chuyên môn công nghệ thông tin: ngồi cùng điều độ viên trong ca chốt booking buổi chiều, đối chiếu bảng tổng hợp booking với danh sách xe rảnh, gọi xác nhận với kho khi tài xế báo về, và tổng hợp chứng từ giao nhận cuối ngày. Phần này chiếm phần lớn thời gian tuần đầu và là nguồn của toàn bộ hiểu biết nghiệp vụ trong báo cáo.

Phần thứ hai là công việc kỹ thuật: xây dựng hệ thống Fleet Fuel Management. Bảng 3.1 liệt kê các hạng mục theo thứ tự thời gian, đối chiếu với lịch sử commit của kho mã nguồn.

**Bảng 3.1. Các hạng mục công việc kỹ thuật theo mốc thời gian**

<!-- nguồn: docs/CHANGELOG.md, các mục có ngày; git log --reverse (commit đầu tiên 2026-07-09) -->

| Mốc | Hạng mục | Kết quả |
|---|---|---|
| 09/7/2026 | Khởi tạo kho mã nguồn, dựng khung ứng dụng Flask | Commit đầu tiên |
| 17–18/7 | Phân hệ xếp hàng ba chiều, giai đoạn 1–2 | Cấu hình thùng xe, tính điểm sử dụng không gian |
| 23/7 | Đồng bộ số km bảo dưỡng từ TTAS | Bản ghi km đầu tiên |
| 29–31/7 | Tái cấu trúc: tách tầng, viết bộ kiểm thử, gỡ đăng nhập | 4 blueprint theo miền nghiệp vụ |
| 31/7 | Định tuyến theo ràng buộc phương tiện, giai đoạn A–C | Hồ sơ xe tải nặng cho ORS |
| 01–03/8 | Phân hệ kế hoạch giao hàng: pha điểm dừng, hoàn tác, ảnh bắt buộc | Kế hoạch đầu tiên chạy thật 01/8 |
| 02/8 | Xuất báo cáo cuối ngày, gắn ổ đĩa lưu trữ lâu dài | Ảnh và cơ sở dữ liệu sống qua lần triển khai lại |
| 03/8 | Sửa lỗi đọc trạng thái tốc độ từ TTAS | Xem mục 3.4.3 |
| 06/8 | Rà soát toàn hệ thống, sửa lỗi giao dịch geofence | Xem mục 3.4.3 |
| 07/8 | Phát hiện bản chạy thật thiếu 14 tuyến đường | Xem mục 3.4.3 |
| 09/8 | Nhập kế hoạch trực tiếp từ Google Sheet của quản lý | Bỏ bước nhập tay |
| 10/8 | Tách ảnh xếp hàng theo tài xế; chuyển pha là quyết định của điều độ viên | Gỡ tự động chuyển pha |
| 13–16/8 | Công cụ đo khoảng cách, ảnh đường phố trên bản đồ điều độ | Hỗ trợ điều độ viên xác minh điểm giao |

## 3.2. Các mục tiêu của công việc, vấn đề cần giải quyết

### 3.2.1. Bốn vấn đề được xác định

Sau tuần khảo sát, bốn vấn đề được đặt ra cùng người hướng dẫn.

**Vấn đề 1 — Trạng thái chuyến hàng chỉ tồn tại trong đầu điều độ viên.** Quy định cấm tài xế liên lạc trực tiếp với khách hàng [13] khiến Phòng Điều độ là nguồn thông tin duy nhất. Khi điều độ viên đang gọi điện cho một xe thì trạng thái của các xe còn lại không được cập nhật. Nền tảng TTAS có vị trí GPS nhưng không nói được xe đó đang đi giao cho ai và đã giao xong mấy điểm.

**Vấn đề 2 — Không có cách phát hiện hao hụt nhiên liệu.** 323 phiếu đổ trong 36 ngày được nhập tay vào Excel. Việc xét một phiếu có bất thường hay không dựa vào trí nhớ của người phụ trách. Với 31 xe phát sinh và trung bình 9 phiếu mỗi ngày, cách này không kiểm soát được.

**Vấn đề 3 — Chứng từ giao nhận không tra cứu được.** Ảnh giao nhận gửi qua Zalo. Khi khách khiếu nại một chuyến của tuần trước, người phụ trách phải cuộn ngược nhóm chat để tìm.

**Vấn đề 4 — Kế hoạch giao hàng phải nhập lại bằng tay.** Quản lý lập kế hoạch trên Google Sheet do chính họ sở hữu; điều độ viên đọc và chép lại. Sheet này viết tay hoàn toàn, và các dạng dữ liệu lệch chuẩn quan sát được trong tài liệu thật ngày 09/8/2026 gồm: cột ngày là chữ với bốn dạng viết khác nhau (`21-Jul`, `2-Aug`, `10-Aug`, `01-th8`), dòng nối tiếp bỏ trống ô ngày, và cột tọa độ có ba định dạng không tương thích — `9,636058` dùng dấu phẩy thập phân, `9.60967` chuẩn, và `9.585.868` trong đó dấu phân cách hàng nghìn đã thay thế dấu thập phân.

<!-- nguồn: docstring module services/delivery/sheet_import_service.py, ghi lại các giá trị quan sát trong tài liệu thật ngày 2026-08-09 -->

Dạng thứ ba là dạng nguy hiểm nhất: `float("9.585.868")` sẽ báo lỗi, nhưng nếu bộ phân tích chỉ đơn giản bỏ dấu chấm thì tọa độ 9,585868 trở thành một con số nằm ở tỉnh khác. Đây là dạng lỗi im lặng — không có ngoại lệ nào được ném ra, chỉ có một điểm giao hàng nằm sai chỗ trên bản đồ.

### 3.2.2. Ràng buộc thiết kế

Bốn ràng buộc được thống nhất trước khi viết dòng mã đầu tiên:

1. **Không được làm chậm ca điều độ.** Bộ phận này làm việc theo giờ chốt cố định. Mọi thao tác thêm vào quy trình phải nhanh hơn thao tác nó thay thế, nếu không sẽ bị bỏ.
2. **Chỉ đọc, không ghi vào nguồn dữ liệu của người khác.** Google Sheet kế hoạch thuộc sở hữu của quản lý; hệ thống chỉ được đọc. Điểm truy cập duy nhất được dùng là điểm truy vấn công khai `gviz/tq` của Google, vốn không có đường ghi nào.
3. **Hệ thống phải chạy được khi TTAS hoặc dịch vụ định tuyến ngoài bị lỗi.** Hạ tầng mạng ở kho không ổn định.
4. **Không thêm bước đăng nhập.** Yêu cầu của đơn vị: hệ thống chạy trên mạng nội bộ, thao tác đăng nhập ở mỗi lần đổi ca làm mất thời gian của điều độ viên.

Ràng buộc thứ tư là một quyết định của đơn vị mà em không đồng ý về mặt kỹ thuật. Cách xử lý được nêu ở mục 3.4.2.

## 3.3. Quy trình thực hiện, phương pháp thực hiện

### 3.3.1. Quy trình nghiệp vụ tại Phòng Điều độ

![Hình 3.1. Sơ đồ quy trình điều vận một ngày tại Phòng Điều độ Vận tải](placeholder)

Quy trình một ngày làm việc gồm bảy bước:

1. **Nhận nhu cầu vận chuyển.** Phòng Kinh doanh nhận booking từ khách hàng trong buổi sáng.
2. **Chốt bảng tổng hợp booking.** Bảng tổng hợp được chốt vào buổi chiều [13]; sau thời điểm này, thay đổi phải được xử lý như phát sinh.
3. **Xếp xe — tài xế — tuyến.** Điều độ viên đối chiếu tải trọng hàng với loại xe, vị trí xe hiện tại, lịch bảo dưỡng và thời gian lái liên tục của tài xế. Đo trên dữ liệu tháng 8/2026: trung bình 4,4 xe và 3,9 điểm dừng mỗi xe mỗi ngày.
4. **Giao lệnh cho tài xế.** Tài xế nhận điểm nhận hàng, danh sách điểm giao theo thứ tự, và yêu cầu chứng từ.
5. **Theo dõi hành trình.** Tài xế báo về Phòng Điều độ khi đến và khi rời mỗi điểm. Tài xế không được liên lạc trực tiếp với khách hàng hoặc nhân viên hiện trường [13].
6. **Thu chứng từ.** Tài xế chụp ảnh theo quy định tại kho xuất và kho đích, gồm ảnh niêm phong trước và sau khi mở, biên bản giao nhận có chữ ký bên nhận, và ảnh toàn cảnh xe [13].
7. **Xử lý sự cố.** Chậm quá ngưỡng thời gian cam kết phải lập biên bản sự cố có đóng dấu công ty [13].

Bước 5 và 6 là hai bước hệ thống can thiệp trực tiếp. Bước 3 chỉ được hỗ trợ bằng số liệu, không tự động hóa.

### 3.3.2. Kiến trúc hệ thống

[[CHO TRONG: Hình 3.2. Kiến trúc ba tầng của hệ thống Fleet Fuel Management và các hệ thống ngoài]]

Hệ thống là ứng dụng web ba tầng.

**Bảng 3.2. Thành phần công nghệ**

<!-- nguồn: đọc requirements.txt (mã hóa UTF-16, phải đọc bằng open(...,'rb').read().decode('utf-16')), app/__init__.py, render.yaml -->

| Tầng | Công nghệ | Ghi chú |
|---|---|---|
| Giao diện | HTML, JavaScript thuần, Leaflet [18], Chart.js [19] | 9 trang, không dùng framework giao diện |
| Ứng dụng | Python, Flask 3.1.3 [14], 7 blueprint | Mẫu app factory `create_app()` |
| Dữ liệu | SQLite [15], 25 bảng, SQL thuần không dùng ORM | Không có tầng ánh xạ đối tượng |
| Triển khai | Gunicorn trên Render, ổ đĩa lưu trữ lâu dài 20 GB | Cơ sở dữ liệu và ảnh sống qua lần triển khai lại |
| Hệ thống ngoài | TTAS (định vị), OpenRouteService [16], Google Sheets | Đều có đường dự phòng khi lỗi |

Quy mô mã nguồn đo tại thời điểm viết báo cáo: 16 064 dòng Python trong các thư mục `app/`, `services/`, `truck_load_planner/`, và 14 364 dòng JavaScript trong `static/js/`.

<!-- nguồn: find app services truck_load_planner -name "*.py" | xargs wc -l | tail -1 → 16064; find static/js -name "*.js" | xargs wc -l | tail -1 → 14364 — chạy 2026-08-16 -->

Tầng ứng dụng chia theo miền nghiệp vụ thành 7 blueprint, tổng cộng 130 tuyến đường.

**Bảng 3.3. Phân bố tuyến đường theo blueprint**

<!-- nguồn: đếm số decorator .route( trong từng tệp — chạy 2026-08-16 -->

| Blueprint | Tệp | Số tuyến | Phạm vi |
|---|---|---|---|
| `delivery_bp` | `services/delivery/routes.py` | 44 | API kế hoạch giao hàng, thực thi, ảnh, xuất báo cáo |
| `tlp_bp` | `truck_load_planner/routes.py` | 28 | API xếp hàng ba chiều |
| `fuel` | `app/routes/fuel.py` | 18 | Nhật ký nhiên liệu, thống kê, phát hiện bất thường |
| `core` | `app/routes/core.py` | 15 | Trang giao diện, danh mục xe, vùng địa lý, mã hóa địa chỉ |
| `fleet` | `app/routes/fleet.py` | 12 | Quản lý phương tiện, thông số kỹ thuật |
| `oil` | `app/routes/oil.py` | 9 | Bảo dưỡng, đồng bộ số km |
| `trips` | `app/routes/trips.py` | 4 | Chuyến hàng, làm mới dữ liệu định tuyến nền |
| | **Tổng** | **130** | |

Không dùng ORM là một quyết định có chủ đích: truy vấn thống kê nhiên liệu và truy vấn bảng điều khiển điều độ đều là các phép nối nhiều bảng kèm tổng hợp, viết thẳng bằng SQL vừa ngắn hơn vừa dễ đọc kế hoạch thực thi hơn. Đổi lại, mọi truy vấn phải dùng tham số `?` chứ không được nối chuỗi — đây là bề mặt tấn công tiêm SQL duy nhất của hệ thống, và là quy tắc bắt buộc ghi trong tài liệu hướng dẫn của kho mã nguồn.

### 3.3.3. Lấy dữ liệu định vị từ hệ thống không có API

TTAS là ứng dụng web ASP.NET WebForms không cung cấp API công khai. Giải pháp là điều khiển một trình duyệt Chromium không giao diện bằng Playwright [17] để đăng nhập, lấy cookie phiên, rồi dùng cookie đó gọi trực tiếp các điểm truy cập dữ liệu bên trong bằng HTTP. Cách này chỉ trả giá thời gian khởi tạo trình duyệt một lần cho mỗi phiên, các lần lấy dữ liệu sau là gọi HTTP thuần.

Dữ liệu trả về không có trường tốc độ dạng số. Trường `speed` của TTAS là **một câu tiếng Việt mô tả trạng thái**, với các dạng quan sát được: `Chạy 42km/h`, `Dừng 3h30'`, `MTH:6h48'`. Mọi con số km/h hiển thị trên bảng điều khiển đều là kết quả trích xuất từ câu chữ này. Hệ quả của việc trích xuất sai được phân tích ở mục 3.4.3.

Ba dạng câu được ánh xạ như sau:

**Bảng 3.4. Ánh xạ chuỗi trạng thái của TTAS sang giá trị tốc độ**

<!-- nguồn: đọc hàm _parse_speed_kmh và các chuỗi mẫu ghi trong CLAUDE.md mục "TTAS telemetry conventions" -->

| Chuỗi TTAS | Ý nghĩa | Giá trị tốc độ | Ghi chú |
|---|---|---|---|
| `Chạy 42km/h` | Xe đang chạy 42 km/h | 42,0 | Chỉ nhận số khi có đơn vị km/h đi kèm |
| `Dừng 3h30'` | Xe đã dừng 3 giờ 30 phút | 0,0 | Số trong chuỗi là thời lượng, không phải tốc độ |
| `MTH:6h48'` | Mất tín hiệu 6 giờ 48 phút | Không xác định | TTAS tự khai báo thiết bị không liên lạc được |
| Dạng chưa biết | — | Không xác định | Trả về "không xác định" thay vì đoán |

Phân biệt giữa "không xác định" và 0,0 là phân biệt có ý nghĩa nghiệp vụ: giao diện hiển thị ô trống cho trường hợp thứ nhất và hiển thị tốc độ 0 cho trường hợp thứ hai. "Không xác định" nghĩa là không đọc được, không phải là xe đang đứng yên.

Một xe mất tín hiệu vẫn có tọa độ — tọa độ của lần định vị cuối trước khi mất. Mọi phép kiểm tra dạng "xe này có GPS không?" đều trả lời là có. Đây chính là lý do các xe mất tín hiệu từng không xuất hiện trong bộ lọc "Không có GPS" của bảng điều khiển, và là lý do hệ thống giữ song song hai đường suy luận: khai báo `MTH` của chính TTAS, và phép tính "dấu thời gian đã cũ" do hệ thống tự tính.

### 3.3.4. Hàng rào địa lý

Vùng kho bãi được lưu dưới dạng đa đa giác. Khi cần kiểm tra một xe có nằm trong vùng hay không, hệ thống chạy thuật toán ray casting theo quy tắc chẵn — lẻ [5] trên từng đa giác thành phần; nằm trong bất kỳ mảnh nào thì coi là nằm trong vùng.

Khoảng cách tới tâm vùng dùng công thức haversine [6] với bán kính 6 371 000 m, cài đặt trong `app/utils/geo.py`. Tâm vùng tính bằng công thức trọng tâm đa giác có trọng số diện tích; với đa đa giác, tâm là trung bình các trọng tâm thành phần có trọng số là diện tích từng mảnh. Trường hợp đa giác suy biến (diện tích xấp xỉ 0) được xử lý riêng bằng cách lấy trung bình cộng các đỉnh, tránh phép chia cho số gần 0.

<!-- nguồn: đọc app/utils/geo.py — hàm get_distance_meters (R = 6371000), calculate_polygon_centroid (ngưỡng suy biến 1e-10), calculate_multi_polygon_centroid -->

### 3.3.5. Định danh phương tiện và tài xế

Biển số cùng một xe xuất hiện trong ba nguồn dữ liệu với ba cách viết khác nhau — `50H 19793`, `50H-197.93`, `51D08660` đều được quan sát trong tài liệu thật. Nếu so khớp bằng chuỗi thô thì một xe sẽ thành ba xe.

Giải pháp là một tầng định danh riêng: chuẩn hóa biển số về một dạng chính tắc duy nhất, dựng chỉ mục theo dạng đó, và so khớp theo phần số 5 chữ số. Toàn hệ thống chỉ có một hàm chuẩn hóa duy nhất (`services/plate_utils.py::normalize_plate`); mọi nơi khác gọi lại nó. Đây là bài học từ môn Cơ sở dữ liệu áp dụng cho dữ liệu ngoài cơ sở dữ liệu: một khái niệm, một biểu diễn chính tắc.

Tên tài xế được xử lý khác. Tên trong bảng kế hoạch của quản lý có lỗi chính tả (`TRẦN` viết thành `TRẬN`) và có dòng ghi nhầm ghi chú vào ô tên. Nếu tự động tạo bản ghi tài xế từ các chuỗi này thì danh mục tài xế sẽ đầy bản ghi rác. Vì vậy tên nhập từ bảng kế hoạch được ghi vào trường ghi đè `driver_name_override` của bảng phân công, và **không** tạo bản ghi trong bảng `drivers`. Bảng `drivers` chỉ nhận tên đã được người dùng xác nhận — hiện có 2 bản ghi.

<!-- nguồn: docstring services/delivery/sheet_import_service.py; SELECT COUNT(*) FROM drivers → 2 -->

### 3.3.6. Phân hệ xếp hàng ba chiều

Phân hệ xếp hàng nhận danh sách kiện hàng và một cấu hình thùng xe, trả về vị trí đặt từng kiện. Thuật toán là heuristic dựng lời giải theo điểm ứng viên: với mỗi kiện, duyệt tập vị trí khả dĩ và các hướng xoay, chấm điểm từng phương án, chọn phương án điểm cao nhất.

Các ràng buộc thực tế trong [10] được mã hóa thành các thành phần của hàm chấm điểm, mỗi thành phần có một trọng số.

**Bảng 3.5. Trọng số hàm chấm điểm của phân hệ xếp hàng**

<!-- nguồn: đọc hằng SCORING_WEIGHTS trong truck_load_planner/engine/scorer.py — chạy 2026-08-16 -->

| Thành phần | Trọng số | Ràng buộc thực tế tương ứng |
|---|---|---|
| `contact_area` | 1000 | Diện tích tiếp xúc với các mặt xung quanh — kiện càng tựa chắc càng ít xê dịch |
| `x_position` | 200 | Mức hoàn tất của lớp hàng hiện tại theo chiều dọc thùng |
| `weight_balance` | 50 | Phân bố tải trọng dọc thùng xe |
| `usable_space` | 3 | Phần không gian còn dùng được sau khi đặt kiện |
| `stack_level` | 1 | Số tầng xếp chồng |
| `tower_height` | 1 | Chiều cao cột hàng |

Trọng số `usable_space` bằng 3 chứ không phải 1 là kết quả của một lần sửa lỗi có ghi lại lý do trong mã nguồn: mức phạt cho việc để lại một dải không gian chết là −1500 điểm, trong khi điểm tối đa của `contact_area` là 1000. Khi trọng số `usable_space` còn bằng 1, một phương án đặt có diện tích tiếp xúc tốt vẫn thắng dù nó để lại khoảng trống không kiện nào lọt vừa. Nhân trọng số lên 3 làm mức phạt luôn thắng.

Đây là ví dụ cụ thể cho nhận xét ở mục 1.1.4: hàm chấm điểm là nơi các ràng buộc thực tế được mã hóa thành số, và giá trị các con số đó chỉ đúng khi đối chiếu với nhau, không đúng một cách độc lập.

Cơ sở dữ liệu hiện có 35 cấu hình thùng xe. Cấu hình xe 2,5 tấn có kích thước lòng thùng 4285 × 1850 × 1810 mm và giới hạn tải 1600 kg — đây là cấu hình được dùng nhiều nhất do loại xe này chiếm 41,7% đội xe (Bảng 2.4).

<!-- nguồn: SELECT COUNT(*) FROM container_configs → 35; SELECT * FROM container_configs LIMIT 2 → hàng "Standard 2.5 tons": 4285.0, 1850.0, 1810.0, 1600.0 -->

### 3.3.7. Đọc kế hoạch từ Google Sheet của quản lý

Bảng kế hoạch thuộc sở hữu của quản lý nên hệ thống chỉ đọc. Điểm truy cập được dùng là `gviz/tq` của Google — điểm truy vấn công khai, không có đường ghi, nên không có nhánh mã nào có thể sửa tài liệu gốc kể cả do lỗi. Tài liệu được chia sẻ theo liên kết nên không cần thông tin xác thực.

Bộ phân tích phải xử lý các dạng lệch chuẩn đã nêu ở mục 3.2.1:

**Bảng 3.6. Các dạng dữ liệu lệch chuẩn và cách xử lý**

<!-- nguồn: docstring module services/delivery/sheet_import_service.py, ghi các giá trị quan sát trong tài liệu thật ngày 2026-08-09 -->

| Dạng quan sát được | Ví dụ thật | Cách xử lý |
|---|---|---|
| Ngày viết bằng chữ, không có năm | `21-Jul`, `2-Aug`, `01-th8` | Nhận cả bốn dạng, suy năm từ ngữ cảnh kế hoạch |
| Dòng nối tiếp bỏ trống ô ngày | 2 dòng trong tháng 8 | Điền xuôi giá trị ngày trước khi so khớp |
| Tọa độ dùng dấu phẩy thập phân | `9,636058` | Đổi dấu phẩy thành dấu chấm |
| Tọa độ bị thay dấu thập phân bằng dấu phân cách nghìn | `9.585.868` → 9,585868 | Nhận diện theo số nhóm chữ số, ghép lại đúng |
| Chỉ dòng đầu mỗi khối xe có biển số và tên tài xế | — | Điền xuôi trong phạm vi khối |
| Biển số viết ba kiểu | `50H 19793`, `50H-197.93` | Chuyển sang tầng định danh (mục 3.3.5) |
| Tên tài xế sai chính tả hoặc là ghi chú | `TRẬN` thay vì `TRẦN` | Ghi vào trường ghi đè, không tạo bản ghi tài xế |

Kết quả của bước nhập là danh sách dòng cùng **một danh sách cảnh báo** để điều độ viên xem lại trước khi xác nhận. Đây là quyết định thiết kế quan trọng: bộ phân tích không tự quyết khi dữ liệu mơ hồ, nó nêu ra và để người quyết.

### 3.3.8. Phát hiện bất thường nhiên liệu

Đường cơ sở của mỗi xe là trung bình trượt mức tiêu hao (lít/100 km) của 5 phiếu đổ gần nhất của chính xe đó. Một phiếu bị gắn cờ bất thường khi mức tiêu hao của nó vượt đường cơ sở nhân với một hệ số ngưỡng.

Hệ số ngưỡng phụ thuộc loại xe: 1,50 cho xe container và 1,20 cho các loại còn lại.

<!-- nguồn: đọc app/routes/fuel.py — hàm _compute_baseline (trung bình 5 phiếu gần nhất), _apply_anomaly_flag (điều kiện l_per_100km > baseline × anomaly_multiplier), và mặc định 1.50 nếu vehicle_type chứa "Container", ngược lại 1.20 -->

Ngưỡng rộng hơn cho xe container phản ánh một thực tế nghiệp vụ: mức tiêu hao của đầu kéo phụ thuộc mạnh vào việc chuyến đó kéo container đầy hay chạy rỗng, và dữ liệu tải trọng từng chuyến không có trong hệ thống. Dùng chung ngưỡng 1,20 cho cả hai loại sẽ khiến mọi chuyến kéo hàng nặng đều bị gắn cờ, và cảnh báo bị gắn cờ quá nhiều thì không ai đọc.

Phiếu thiếu số km cũ hoặc số km mới không tính được lít/100 km. Các phiếu này vẫn được lưu vào nhật ký nhưng bị loại khỏi phép tính đường cơ sở và khỏi thống kê — hiện có 4 phiếu như vậy trên tổng số 323.

Với các xe chưa đủ 5 phiếu lịch sử, hệ thống cho phép nhập một giá trị định mức tĩnh thay cho đường cơ sở tính được. Hiện có 2 xe đang dùng định mức tĩnh.

<!-- nguồn: SELECT COUNT(*) FROM fuel_vehicle_profile → 2 -->

### 3.3.9. Đường dự phòng khi dịch vụ ngoài lỗi

Ràng buộc thứ ba ở mục 3.2.2 được cài đặt như sau:

**Bảng 3.7. Hành vi của hệ thống khi từng hệ thống ngoài không khả dụng**

| Hệ thống ngoài | Khi lỗi | Hành vi thay thế |
|---|---|---|
| OpenRouteService | Không có lộ trình theo đường bộ | Tính khoảng cách đường chim bay bằng haversine [6], ghi rõ là ước lượng |
| TTAS | Không lấy được vị trí mới | Dùng vị trí trong bộ nhớ đệm, hiển thị dấu thời gian đã cũ |
| Google Sheet | Không đọc được kế hoạch | Giữ nguyên nhập tay bằng tệp Excel |

Thời gian đến dự kiến được lưu đệm theo từng lượt phân công, khóa đệm gồm danh sách điểm dừng còn lại và vị trí GPS; vị trí thay đổi dưới 50 m được coi là không đổi để tránh gọi lại dịch vụ định tuyến ở mỗi vòng thăm dò.

<!-- nguồn: đọc services/delivery/eta_service.py — ROUTE_CACHE_GPS_THRESHOLD_M = 50 -->

## 3.4. Kết quả đạt được

### 3.4.1. Những việc đã thực hiện

**Hệ thống chạy trên môi trường thật.** Fleet Fuel Management được triển khai trên nền tảng Render bằng Gunicorn, có ổ đĩa lưu trữ lâu dài 20 GB gắn tại `/var/data` để cơ sở dữ liệu và thư mục ảnh giao nhận sống qua mỗi lần triển khai lại. Bộ phận Điều độ sử dụng hệ thống liên tục từ 01/8/2026; tính đến 16/8/2026 đã có 14 ngày kế hoạch chạy trên hệ thống chứ không phải chạy thử.

**Kết quả đo được sau khi triển khai** được tổng hợp ở Bảng 3.8. Cần đọc bảng này cùng với lưu ý ở mục 1.3: các đại lượng dưới đây chỉ đo được **sau** khi có hệ thống, vì trước đó không có cơ chế nào ghi lại chúng.

**Bảng 3.8. Đại lượng đo được trên hệ thống, tính đến 16/8/2026**

<!-- nguồn: các truy vấn SQL liệt kê trong Phụ lục A, chạy trên routing_system.db ngày 2026-08-16 -->

| Đại lượng | Giá trị | Trước khi có hệ thống |
|---|---|---|
| Kế hoạch giao hàng được số hóa | 14 ngày | Google Sheet chép tay |
| Lượt xe được phân công có lưu vết | 62 | Không lưu vết |
| Điểm dừng có trạng thái thực thi | 243 | Không lưu vết |
| Sự kiện đổi trạng thái điểm dừng được ghi | 472 | Không có |
| Ảnh giao nhận lưu trong cơ sở dữ liệu | 3 333 | Nằm trên Zalo |
| Điểm dừng có ảnh | 105 / 243 | Không đếm được |
| Ảnh trung bình mỗi điểm dừng có ảnh | 31,7 | Không đếm được |
| Phiếu nhiên liệu được kiểm tra bất thường tự động | 323 | Kiểm bằng trí nhớ |
| Lần đồng bộ dữ liệu ngoài được ghi nhật ký | 22 | Không có |
| Phương án xếp hàng được lưu | 18 | Không có bản vẽ |

Con số 3 333 ảnh cần đọc cẩn thận. Ảnh mới được nộp cho 105 trên 243 điểm dừng, tức 43,2%; trung bình mỗi điểm **có ảnh** nhận 31,7 ảnh, cao hơn nhiều so với quy định chụp tại kho xuất và kho đích [13], vì tài xế chụp nhiều lần cho mỗi hạng mục để chắc chắn có ảnh rõ. Tỷ lệ 43,2% không có nghĩa là 57% điểm dừng thiếu chứng từ: phần lớn ảnh của giai đoạn đầu vẫn nằm trên Zalo và chỉ những chuyến sau khi phân hệ ảnh được đưa vào dùng mới có ảnh trong cơ sở dữ liệu.

<!-- nguồn: SELECT COUNT(DISTINCT stop_id) FROM delivery_stop_images → 105; SELECT COUNT(*) FROM delivery_stop_images → 3333 -->

**Bộ kiểm thử tự động.** Toàn bộ 16 bộ kiểm thử Python chạy qua với 737 trường hợp kiểm thử. Kho mã nguồn không có hệ thống tích hợp liên tục, nên việc tự chạy lại toàn bộ sau mỗi thay đổi là cách kiểm chứng duy nhất.

**Bảng 3.9. Kết quả chạy bộ kiểm thử ngày 16/8/2026**

<!-- nguồn: python3 -m pytest tests/<tệp> -q, chạy lần lượt từng tệp ngày 2026-08-16; tổng hợp: pytest tests/ -q → "737 passed in 71.21s" -->

| Bộ kiểm thử | Số trường hợp | Phạm vi |
|---|---|---|
| `test_delivery.py` | 230 | Tầng dịch vụ kế hoạch giao hàng |
| `test_delivery_routes.py` | 157 | Tầng tuyến đường kế hoạch giao hàng |
| `test_sheet_import.py` | 89 | Bộ phân tích Google Sheet |
| `test_vehicle_specs.py` | 40 | Thông số kỹ thuật, ràng buộc định tuyến |
| `test_vehicle_core_data.py` | 36 | Dữ liệu phương tiện chỉ đọc với tiến trình nền |
| `test_write_handler_connections.py` | 36 | Đóng kết nối ở các trình xử lý ghi |
| `test_streetview_routes.py` | 30 | Ảnh đường phố trên bản đồ điều độ |
| `test_sheet_import_routes.py` | 26 | Điểm truy cập nhập kế hoạch |
| `test_scorer.py` | 26 | Hàm chấm điểm xếp hàng |
| `test_routing.py` | 15 | Định tuyến, đường dự phòng |
| `test_trips_geofence.py` | 14 | Hàng rào địa lý, tiến trình nền |
| `test_fleet_routes.py` | 11 | Quản lý phương tiện |
| `test_tlp_routes.py` | 8 | Điểm truy cập xếp hàng |
| `test_wsgi_routes.py` | 8 | Đối chiếu bản chạy thật với bản phát triển |
| `test_fuel_routes.py` | 6 | Điểm truy cập nhiên liệu |
| `test_auto_arrange_e2e.py` | 5 | Xếp hàng tự động, đầu cuối |
| **Tổng** | **737** | |

Ngoài ra còn 7 bộ kiểm thử JavaScript cho phần giao diện, chạy bằng Node. Số trường hợp trong các tệp này được đếm tĩnh: 130 (bảng điều khiển), 35 (công cụ đo), 33 (ảnh đường phố), 16 (nhập kế hoạch), 12 (xuất báo cáo), 10 (trình dựng kế hoạch), 5 (thoát ký tự) — tổng 241. Em **không** chạy được các bộ này trong môi trường viết báo cáo do thiếu thư viện `jsdom`, nên con số 241 là số hàm kiểm thử được khai báo, không phải số trường hợp đã chạy qua.

<!-- nguồn: grep -cE "^\s*(test|it)\(" tests/js/*.js — chạy 2026-08-16. Không chạy được bằng node trong môi trường sandbox. -->

**Quy trình sửa lỗi.** Với mỗi lỗi được sửa, quy trình áp dụng là: viết kiểm thử tái hiện lỗi, hoàn tác bản sửa để xác nhận kiểm thử **thất bại**, rồi khôi phục bản sửa. Bước hoàn tác là bước hay bị bỏ và cũng là bước có giá trị nhất — nhiều kiểm thử trong các bộ trên vẫn xanh khi chạy trên mã nguồn còn lỗi trước khi quy trình này thành thói quen.

### 3.4.2. Đề xuất cải thiện công việc tại phòng ban

**Đề xuất 1 — Sửa nguồn thay vì sửa hệ quả.** Bảng kế hoạch của quản lý là nguồn của phần lớn công sức phân tích ở mục 3.3.7. Một ví dụ cụ thể: cột số điện thoại người phụ trách điểm giao được Google Sheets lưu ở dạng số cho một số dòng, làm mất chữ số 0 đầu; khi đọc qua điểm truy cập `gviz`, ô đó về dưới dạng `939746130.0`, và bước làm sạch giữ luôn chữ số 0 sau dấu chấm thập phân. Kết quả: trong 149 điểm dừng có số điện thoại, 118 số bị hỏng — 33 số chỉ còn 9 chữ số, và 85 số có 10 chữ số kết thúc bằng 0. Cả 85 trên 85 số nhóm sau đều kết thúc bằng 0, tỷ lệ không thể xảy ra với số điện thoại thật, và chính sự đồng loạt đó xác định nguyên nhân là kiểu dữ liệu số chứ không phải người nhập sai.

<!-- nguồn: docs/CHANGELOG.md mục 2026-08-15 "Stop manager phone numbers were unusable in 118 of 149 stops" -->

Đặt định dạng cột số điện thoại và cột tọa độ về dạng văn bản trong Google Sheet là thao tác một lần, mất vài giây, và loại bỏ vĩnh viễn cả một lớp lỗi. Đề xuất này đã được trình bày với người hướng dẫn.

**Đề xuất 2 — Bổ sung cột tải trọng thực tế vào bảng kế hoạch.** Ngưỡng phát hiện bất thường của xe container phải nới rộng lên 1,50 (mục 3.3.8) chỉ vì hệ thống không biết chuyến đó chở nặng hay chạy rỗng. Nếu bảng kế hoạch ghi thêm khối lượng hàng thực tế, ngưỡng có thể tính theo tải trọng thay vì theo loại xe, và độ nhạy phát hiện sẽ tăng mà không tăng cảnh báo giả.

**Đề xuất 3 — Đo lại khối lượng thao tác thủ công trước khi thay đổi tiếp theo.** Không có mốc so sánh cho chỉ tiêu "giảm 80% thao tác thủ công" là một thiếu sót có thể tránh được. Với bất kỳ quy trình nào sắp được số hóa, đề xuất đo trước: số phút mỗi ngày, số lần nhập liệu, số lần phải hỏi lại. Việc đo mất một buổi và làm mọi báo cáo sau đó có căn cứ.

**Đề xuất 4 — Xem lại quyết định không có xác thực khi phạm vi mạng thay đổi.** Hệ thống hiện không có bước đăng nhập, kể cả cho các thao tác xóa dữ liệu. Quyết định này hợp lý với điều kiện hiện tại — chạy trên mạng nội bộ, và bước đăng nhập ở mỗi lần đổi ca là chi phí thật với điều độ viên. Nhưng nó chỉ hợp lý *với điều kiện đó*. Nếu hệ thống được mở ra internet, hoặc nếu tài xế truy cập từ điện thoại ngoài mạng công ty, đây là việc phải bàn lại trước tiên. Ràng buộc này được ghi lại trong tài liệu kho mã nguồn kèm một kiểm thử tự động xác nhận trạng thái mở, để nó là một quyết định được ghi nhận chứ không phải một thiếu sót bị bỏ quên.

### 3.4.3. Những việc chưa làm được

**Tự động chuyển pha chuyến hàng bằng geofence — đã cài đặt rồi gỡ bỏ.** Đây là mục tiêu số 3 ở Bảng 1.3 và là phần em kỳ vọng nhất khi bắt đầu. Cơ chế hoạt động đúng như thiết kế: tiến trình nền kiểm tra vị trí xe với vùng đích của pha hiện tại, nằm trong vùng thì tự chuyển sang pha kế tiếp. Nó bị gỡ ngày 10/8/2026 vì hai lý do, và cả hai đều không phải lỗi thuật toán.

Lý do thứ nhất là nghiệp vụ: một xe đi ngang qua vùng kho không có nghĩa là nó đã giao hàng xong ở đó. Xe đỗ chờ trước cổng, xe quay đầu, xe giao ở kho kế bên — tất cả đều làm thuật toán chuyển pha nhầm, và điều độ viên phải sửa lại bằng tay. Việc sửa lại tốn thời gian hơn việc tự bấm chuyển pha ngay từ đầu. Chuyển pha nay là quyết định của điều độ viên, hệ thống chỉ hiển thị dữ liệu vị trí để hỗ trợ.

Lý do thứ hai là kỹ thuật, và là lỗi nghiêm trọng nhất em gây ra trong đợt thực tập. Vòng lặp xử lý các chuyến trong tiến trình nền mở một giao dịch ghi rồi thực hiện các lời gọi tới dịch vụ định tuyến bên ngoài **bên trong** giao dịch đó, tuần tự cho từng chuyến. Trong SQLite, một giao dịch ghi giữ khóa cho tới khi commit; giữ khóa qua N lời gọi mạng nghĩa là mọi tiến trình ghi khác đều chờ, và khi vượt quá thời gian chờ mặc định 5 giây thì báo lỗi `database is locked`. Bản sửa là thu hẹp phạm vi giao dịch xuống một vòng lặp thay vì toàn bộ N vòng.

Điều đáng nói là chẩn đoán ban đầu đã sai. Lỗi `database is locked` được cho là do thiếu chế độ ghi trước (WAL) và được ghi lại như vậy trong tài liệu. Khi đo lại ngày 06/8/2026 thì kết luận đó không đúng: SQLite tuần tự hóa các tiến trình ghi trong cả hai chế độ, nên WAL không giải quyết xung đột ghi — ghi. Phép đo với 6 luồng đọc và 1 luồng ghi trong 6 giây cho **0 lỗi khóa ở cả hai chế độ**; nguyên nhân duy nhất của lỗi là giao dịch bị giữ quá lâu.

**Bảng 3.10. Đo hiệu năng hai chế độ nhật ký của SQLite**

<!-- nguồn: docs/CONCURRENCY_PLAN_2026-08-06.md, bảng đo ngày 2026-08-06: 6 luồng đọc + 1 luồng ghi, 6 giây, thời gian chờ mặc định -->

| Chế độ nhật ký | Lượt đọc hoàn tất | Đọc p50 | Đọc p95 | Lượt ghi | Ghi p50 | Ghi p95 | Lỗi khóa |
|---|---|---|---|---|---|---|---|
| `delete` (mặc định) | 924 | 28,5 ms | 81,0 ms | 166 | 24,1 ms | 43,0 ms | 0 |
| `wal` | 2128 | 14,0 ms | 29,5 ms | 511 | 0,8 ms | 4,0 ms | 0 |

WAL vẫn đáng bật vì lý do thông lượng — gấp 2,3 lần lượt đọc, thời gian đọc p95 giảm 64%, thời gian ghi p50 từ 24,1 ms xuống 0,8 ms — nhưng **không** phải vì lý do an toàn như đã ghi trước đó. Đến khi kết thúc đợt thực tập, WAL vẫn chưa được bật: đây là thay đổi trên hệ thống đang chạy thật và cần thời gian theo dõi mà đợt thực tập không còn.

**Chạy nhiều tiến trình xử lý song song — chưa làm.** Bản chạy thật hiện chỉ có một tiến trình xử lý đồng bộ, nên các yêu cầu xếp hàng chờ nhau. Nguyên nhân không cho phép thêm tiến trình không nằm ở cơ sở dữ liệu mà ở trạng thái dùng chung: bộ nhớ đệm dữ liệu định tuyến, phiên kết nối TTAS và ba khóa đồng bộ đều nằm trong bộ nhớ tiến trình. Thêm tiến trình thứ hai nghĩa là có hai bộ nhớ đệm, hai phiên TTAS, và ba khóa kia lặng lẽ mất tác dụng loại trừ lẫn nhau. Đây là vấn đề kiến trúc phải giải trước, không phải một tham số cấu hình.

**Nhắc bảo dưỡng tự động — hoạt động một phần.** Cơ chế đồng bộ số km từ TTAS chạy được, nhưng bảng nhật ký số km hiện chỉ có 1 bản ghi, ghi ngày 23/7/2026. Đồng bộ chưa được đặt lịch chạy định kỳ mà vẫn phải bấm tay, nên dữ liệu không đủ dày để cảnh báo bảo dưỡng có ý nghĩa. Mục tiêu số 6 ở Bảng 1.3 vì vậy chỉ đạt một phần.

<!-- nguồn: SELECT COUNT(*), MIN(log_date), MAX(log_date) FROM oil_km_log → (1, '2026-07-23', '2026-07-23') -->

**Phân hệ xếp hàng chưa được dùng trong vận hành.** 18 phương án xếp hàng đã được lưu, nhưng bảng lô hàng chỉ có 1 bản ghi — nghĩa là phân hệ mới ở mức chạy thử với dữ liệu mẫu, chưa gắn vào quy trình xếp hàng thật tại kho. Nguyên nhân là dữ liệu kích thước kiện hàng chưa có: hàng được xếp theo kinh nghiệm tài xế và không ai đo từng kiện.

<!-- nguồn: SELECT COUNT(*) FROM tlp_load_plans → 18; SELECT COUNT(*) FROM tlp_shipments → 1 -->

**Thông số kỹ thuật phương tiện vẫn là giá trị mặc định theo loại xe.** Định tuyến theo ràng buộc xe tải nặng cần chiều cao, chiều rộng, tổng tải trọng và tải trọng trục của từng xe. Các giá trị này hiện lấy từ bảng mặc định theo loại xe chứ không từ giấy đăng kiểm từng xe. Lộ trình do dịch vụ định tuyến trả về vì vậy đúng ở mức loại xe, chưa đúng ở mức từng xe.

**Một số công việc đã hoàn thành nhưng không đo được hiệu quả.** Đề xuất 3 ở mục 3.4.2 xuất phát từ đây. Việc số hóa ảnh giao nhận rõ ràng thuận tiện hơn Zalo, nhưng em không thể nói nó tiết kiệm bao nhiêu phút mỗi ngày, vì không ai đo thời gian tìm ảnh trên Zalo trước đó.

## 3.5. Phân tích và xử lý số liệu

### 3.5.1. Phương pháp xử lý số liệu

Mọi số liệu trong báo cáo được lấy theo một trong bốn cách: truy vấn SQL trên cơ sở dữ liệu sản xuất, chạy bộ kiểm thử tự động, đọc hằng số trong mã nguồn, hoặc đọc phép đo đã ghi trong tài liệu kho mã nguồn. Câu truy vấn của từng con số được ghi trong chú thích cạnh số đó ở bản Markdown và tổng hợp lại ở Phụ lục A. Số liệu không thuộc bốn nguồn này được đánh dấu `[[CẦN SỐ LIỆU]]` thay vì ước lượng.

### 3.5.2. Phân tích dữ liệu nhiên liệu

**Bảng 3.11. Phân tích 323 phiếu đổ nhiên liệu, 23/6 – 28/7/2026**

<!-- nguồn: truy vấn trên bảng fuel_log, chạy 2026-08-16, xem Phụ lục A mục A.2 -->

| Chỉ tiêu | Giá trị | Cách tính |
|---|---|---|
| Tổng số phiếu | 323 | `COUNT(*)` |
| Số phương tiện phát sinh | 31 / 36 | `COUNT(DISTINCT license_plate)` |
| Tổng lượng nhiên liệu | 19 967,2 lít | `SUM(liters)` |
| Tổng chi phí | 452 679 427 VND | `SUM(liters × unit_price)` |
| Đơn giá bình quân | 22 671 VND/lít | Tổng chi phí ÷ tổng lít |
| Phiếu tính được lít/100 km | 319 (98,8%) | Có đủ km cũ, km mới và km mới > km cũ |
| Phiếu không tính được | 4 (1,2%) | Thiếu km hoặc km mới ≤ km cũ |
| Số ngày trong kỳ | 36 | 23/6 đến 28/7 |
| Bình quân phiếu mỗi ngày | 9,0 | 323 ÷ 36 |
| Bình quân chi phí mỗi ngày | 12,6 triệu VND | 452,7 triệu ÷ 36 |

Tỷ lệ 5 xe trên 36 không phát sinh phiếu đổ nào trong kỳ có hai cách giải thích: xe nằm xưởng, hoặc phiếu của xe đó chưa được nhập. Hệ thống hiện không phân biệt được hai trường hợp này — một hạn chế nữa của việc dữ liệu chỉ có một chiều vào.

Tỷ lệ phiếu thiếu km là 1,2%, thấp hơn dự đoán ban đầu. Con số này chỉ đo được sau khi có hệ thống, vì trên Excel không có ràng buộc nào bắt buộc nhập cột km.

### 3.5.3. Phân tích dữ liệu giao hàng

**Bảng 3.12. Phân tích 14 kế hoạch giao hàng, 01/8 – 16/8/2026**

<!-- nguồn: truy vấn trên delivery_plans, vehicle_assignments, delivery_plan_stops, stop_executions, delivery_stop_images — chạy 2026-08-16, xem Phụ lục A mục A.3 -->

| Chỉ tiêu | Giá trị |
|---|---|
| Số ngày có kế hoạch | 14 / 16 ngày dương lịch |
| Lượt phân công xe | 62 |
| Điểm dừng theo kế hoạch | 243 |
| Điểm dừng đã hoàn tất | 224 (92,2%) |
| Điểm dừng bị hủy | 2 (0,8%) |
| Điểm dừng chưa đến hạn | 17 (7,0%) |
| Tỷ lệ hoàn tất trên số đã đến hạn | 224 / 226 = 99,1% |
| Sự kiện đổi trạng thái được ghi | 472 |
| Ảnh giao nhận | 3 333 |
| Điểm dừng có ít nhất một ảnh | 105 (43,2%) |
| Ảnh bình quân trên điểm dừng có ảnh | 31,7 |

Số sự kiện đổi trạng thái (472) gần gấp đôi số điểm dừng (243). Chênh lệch này là dữ liệu về thao tác sửa: mỗi lần điều độ viên bấm nhầm rồi hoàn tác đều sinh thêm sự kiện. Nhật ký sự kiện được thiết kế để ghi cả thao tác hoàn tác chứ không ghi đè trạng thái cũ, nên nó vừa là dữ liệu nghiệp vụ vừa là dữ liệu về cách hệ thống được sử dụng.

Hai ngày không có kế hoạch trong kỳ là 02/8 và 09/8, đều là Chủ nhật. Chủ nhật không phải ngày nghỉ cố định: 16/8 cũng là Chủ nhật và vẫn có kế hoạch với 17 điểm dừng.

<!-- nguồn: SELECT plan_date FROM delivery_plans; đối chiếu thứ trong tuần bằng datetime.date.fromisoformat().strftime('%A') -->

### 3.5.4. Chất lượng dữ liệu đầu vào

**Bảng 3.13. Tỷ lệ lỗi dữ liệu đo được trên các nguồn đầu vào**

| Nguồn | Trường | Số bản ghi | Số lỗi | Tỷ lệ |
|---|---|---|---|---|
| Bảng kế hoạch Google Sheet | Số điện thoại người phụ trách | 149 | 118 | 79,2% |
| Nhật ký nhiên liệu | Số km cũ / mới | 323 | 4 | 1,2% |
| Bảng kế hoạch Google Sheet | Địa chỉ không phân loại được tỉnh | 243 | 49 | 20,2% |

<!-- nguồn: dòng 1 từ docs/CHANGELOG.md mục 2026-08-15; dòng 2 và 3 từ truy vấn SQL, xem Phụ lục A -->

Bảng 3.13 là lập luận cho Đề xuất 1 ở mục 3.4.2: tỷ lệ lỗi 79,2% ở một trường không đến từ người nhập cẩu thả mà đến từ định dạng ô trong bảng tính. Sửa ở nguồn rẻ hơn sửa ở mọi nơi tiêu thụ dữ liệu.

# CHƯƠNG 4: TỰ ĐÁNH GIÁ VÀ NHẬN XÉT QUÁ TRÌNH THỰC TẬP THỰC TẾ

## 4.1. Nhận thức của bản thân

### 4.1.1. Thuận lợi

Thuận lợi lớn nhất là được ngồi trực tiếp tại Phòng Điều độ trong các ca chốt booking. Phần lớn ràng buộc nghiệp vụ được cài đặt trong hệ thống — quy định luồng thông tin qua điều độ, yêu cầu chứng từ ảnh, ngưỡng thời gian phải lập biên bản — đều đến từ việc quan sát, không đến từ tài liệu. Nếu chỉ nhận đặc tả bằng văn bản rồi ngồi lập trình ở nơi khác, phân hệ kế hoạch giao hàng chắc chắn sẽ được thiết kế sai.

Thuận lợi thứ hai là được quyền triển khai lên môi trường thật và nhận phản hồi trong ngày. Nhiều lỗi trong Bảng 3.1 được người dùng phát hiện chỉ vài giờ sau khi triển khai — điều không xảy ra với một đồ án môn học nộp một lần rồi thôi.

### 4.1.2. Khó khăn và cách giải quyết

**Khó khăn 1 — Không biết bắt đầu từ đâu.** Tuần đầu em có bốn vấn đề (mục 3.2.1) và không có thứ tự ưu tiên. Cách giải quyết là chọn theo tiêu chí "cái nào sinh dữ liệu cho cái khác": phân hệ định vị và định danh phương tiện làm trước vì các phân hệ còn lại đều cần biết xe nào là xe nào.

**Khó khăn 2 — Dữ liệu đầu vào không có hợp đồng.** Chuỗi trạng thái của TTAS là văn bản tiếng Việt do một hệ thống bên thứ ba sinh ra; không có tài liệu, không có cam kết định dạng, và dạng mới có thể xuất hiện bất cứ lúc nào. Cách giải quyết là so khớp khoan dung (bỏ qua khác biệt hoa thường, khoảng trắng, chữ viết tắt) và **rơi về "không xác định" thay vì đoán**. Nguyên tắc này được rút ra sau lỗi ở mục 4.3.1.

**Khó khăn 3 — Không biết mình đã sửa xong hay chưa.** Kho mã nguồn không có hệ thống tích hợp liên tục. Cách giải quyết là quy trình ba bước ở mục 3.4.1: viết kiểm thử, hoàn tác bản sửa để xác nhận kiểm thử thất bại, khôi phục bản sửa. Bước hoàn tác là bước em bỏ trong hai tuần đầu, và đó là lý do một số kiểm thử viết trong giai đoạn đó không thực sự bảo vệ được gì.

**Khó khăn 4 — Sửa lỗi trên hệ thống người khác đang dùng.** Khi bộ phận đã dùng hệ thống hằng ngày thì mỗi lần triển khai là một rủi ro. Cách giải quyết là chỉ thay đổi trong phạm vi đã yêu cầu, không dọn dẹp mã nguồn "tiện tay", và với thay đổi lớn thì chia thành nhiều giai đoạn, mỗi giai đoạn kiểm chứng xong mới sang giai đoạn sau. Phân hệ định tuyến theo ràng buộc phương tiện được làm theo ba giai đoạn A, B, C trong cùng ngày 31/7 theo cách này.

### 4.1.3. Kiến thức và tài liệu cần chuẩn bị

Nhìn lại, ba nhóm kiến thức nếu chuẩn bị trước sẽ tiết kiệm được nhiều thời gian:

1. **SQLite ở mức hệ quản trị chứ không chỉ mức câu lệnh SQL.** Cụ thể là mô hình khóa, phạm vi giao dịch, chế độ nhật ký và thời gian chờ. Lỗi ở mục 3.4.3 là lỗi của người biết viết `SELECT` và `JOIN` nhưng chưa từng nghĩ về việc một giao dịch giữ khóa trong bao lâu.
2. **Kiểm thử tự động như một kỹ năng riêng.** Viết được kiểm thử khác với viết được kiểm thử phát hiện được lỗi.
3. **Đọc mã nguồn của người khác.** Thư viện điều khiển trình duyệt, thư viện bản đồ, thư viện biểu đồ — trong cả ba trường hợp, tài liệu chính thức không trả lời được câu hỏi cụ thể và phải đọc mã nguồn hoặc mã ví dụ.

## 4.2. Học hỏi từ nơi thực tập

### 4.2.1. Kỹ năng chuyên môn

**Bảng 4.1. Kỹ năng chuyên môn được củng cố hoặc học mới**

| Kỹ năng | Trước đợt thực tập | Sau đợt thực tập |
|---|---|---|
| SQL | Viết truy vấn trên dữ liệu bài tập | Thiết kế lược đồ 25 bảng, đặt ràng buộc UNIQUE thay kiểm tra ở ứng dụng, cân nhắc phạm vi giao dịch |
| Kiến trúc ứng dụng web | Viết một tệp duy nhất | Tách 7 blueprint theo miền, mẫu app factory, tách bản chạy thật và bản phát triển |
| Xử lý dữ liệu bẩn | Giả định dữ liệu sạch | Viết bộ phân tích khoan dung cho 7 dạng lệch chuẩn quan sát được (Bảng 3.6) |
| Kiểm thử | Chưa từng viết | 737 trường hợp Python, quy trình kiểm chứng bằng cách hoàn tác bản sửa |
| Lập trình đồng thời | Biết khái niệm khóa | Gặp và tự gây ra lỗi khóa thật, đo lại và bác bỏ chẩn đoán ban đầu |
| Tích hợp hệ thống ngoài | Gọi API có tài liệu | Lấy dữ liệu từ hệ thống không có API, thiết kế đường dự phòng cho từng dịch vụ |
| Đọc và ghi tài liệu kỹ thuật | Viết README | Ghi nhật ký thay đổi có ngày, ghi lại phép đo bác bỏ kết luận cũ thay vì xóa kết luận cũ |

Kỹ năng ở dòng cuối là kỹ năng em không lường trước. Khi phép đo ngày 06/8 cho thấy kết luận về WAL ghi trước đó là sai, cách xử lý là thêm ghi chú có ngày ngay bên cạnh kết luận cũ chứ không sửa kết luận cũ cho khớp. Người đọc sau này cần thấy cả hai: điều đã tin và lý do thôi tin.

### 4.2.2. Nguyên tắc ứng xử tại cơ quan

Quy định cấm tài xế liên lạc trực tiếp với khách hàng [13] ban đầu trông như một quy định cứng nhắc. Sau khi ngồi tại phòng vài ca, em hiểu lý do: khi có sự cố, khách hàng cần nghe một câu trả lời duy nhất, và tài xế đang lái xe không phải người ở vị trí đưa ra câu trả lời đó. Quy định này thực chất là một ràng buộc kiến trúc áp lên tổ chức — cùng nguyên tắc "một nguồn thông tin duy nhất" mà em áp dụng khi thiết kế cơ sở dữ liệu.

Nguyên tắc thứ hai học được là cách trình bày một lỗi. Khi phát hiện hệ thống báo sai tốc độ một xe (mục 4.3.1), phản xạ đầu tiên của em là giải thích nguyên nhân kỹ thuật. Người hướng dẫn tại đơn vị chỉ hỏi: xe đó thực tế đang ở đâu, và bao nhiêu xe khác đang bị báo sai như vậy. Câu hỏi đúng là câu hỏi về phạm vi ảnh hưởng, không phải về nguyên nhân.

### 4.2.3. Tác phong công nghiệp

Điều khác biệt rõ nhất so với môi trường học tập là tính chất theo giờ chốt. Phòng Điều độ làm việc theo mốc thời gian cố định trong ngày; đến giờ là phải có quyết định, kể cả khi thông tin chưa đầy đủ. Trong một lần chạy thử, hệ thống lỗi đúng vào ca chốt, và cách xử lý của bộ phận là quay lại Excel trong ngày hôm đó rồi mới báo lỗi — vận hành không dừng chờ phần mềm. Bài học rút ra được cài đặt thẳng vào hệ thống: mỗi dịch vụ ngoài đều phải có đường dự phòng (Bảng 3.7), vì "hệ thống lỗi thì chờ sửa" không phải một lựa chọn ở đây.

## 4.3. Đánh giá mối liên hệ giữa lý thuyết và thực tiễn

### 4.3.1. Một tình huống cụ thể: trích xuất số từ chuỗi

Đây là tình huống cho thấy rõ nhất khoảng cách giữa cách xử lý ở trường và cách xử lý ở nơi thực tập.

**Tình huống.** Bảng điều khiển hiển thị một xe đang chạy 7 km/h. Thực tế xe đó đã đỗ 7 giờ 44 phút. Chuỗi TTAS trả về là `Dừng 7h44'`, và đoạn mã trích xuất tốc độ dùng biểu thức chính quy lấy **số đầu tiên** trong chuỗi — nó lấy được số 7, vốn là số giờ đỗ, và hiển thị thành tốc độ.

**Cách nghĩ ở trường.** Trong bài tập, đề bài cho biết định dạng đầu vào. "Chuỗi có dạng `Chạy <số>km/h`, hãy trích xuất số" là một bài tập biểu thức chính quy hoàn toàn hợp lệ, và lời giải lấy số đầu tiên sẽ được chấm đúng. Không có bài tập nào nói rằng cùng một trường dữ liệu có thể chứa một đại lượng hoàn toàn khác với cùng kiểu định dạng.

**Cách xử lý ở nơi thực tập.** Bản sửa không phải là một biểu thức chính quy tốt hơn, mà là đảo ngược thứ tự suy luận: đọc **ý nghĩa** của câu trước, rồi mới lấy chữ số. Cụ thể, hàm phân tích chỉ nhận một con số khi nó đi kèm đơn vị km/h; ánh xạ `Dừng` sang giá trị 0,0 đã biết; loại bỏ các cụm thời lượng trước khi thử nhánh dự phòng không đơn vị; và trả về "không xác định" cho mọi dạng chưa biết.

**Phân tích vì sao khác nhau.** Bài tập ở trường có một giả định ngầm mà không ai nói ra: đầu vào tuân theo một hợp đồng. Ở đây không có hợp đồng nào — chuỗi này là kết quả cào từ giao diện của bên thứ ba, có thể đổi bất cứ lúc nào mà không báo. Khi không có hợp đồng, biểu thức chính quy nào cũng chỉ là một phỏng đoán, và điều quan trọng không phải là phỏng đoán đúng mà là **thất bại một cách quan sát được**. Đó là lý do "không xác định" là một giá trị trả về hợp lệ và khác 0,0.

Một chi tiết cho thấy bài học này chưa được áp dụng hết: một chỗ khác trong mã nguồn vẫn còn dùng biểu thức chính quy lấy số đầu tiên. Chỗ này được để lại có chủ đích, ghi rõ trong tài liệu là đã biết sai, vì sửa nó cần thay đổi cả đường dữ liệu của bảng điều khiển chuyến hàng và không nằm trong phạm vi đợt thực tập. Ghi lại một lỗi đã biết mà chưa sửa cũng là một cách xử lý — khác với việc không biết nó tồn tại.

### 4.3.2. Đối chiếu từng môn học

**Bảng 4.2. Môn học và điểm được vận dụng**

| Môn học | Kiến thức vận dụng | Mục trong báo cáo |
|---|---|---|
| Cấu trúc dữ liệu và Giải thuật | Ray casting O(n), trọng tâm đa giác có trọng số diện tích, heuristic dựng lời giải cho bài toán NP-khó | 1.1.2, 1.1.4, 3.3.4, 3.3.6 |
| Cơ sở dữ liệu | Khóa chính/ngoại, UNIQUE, chuẩn hóa, chỉ mục, ACID, phạm vi giao dịch | 1.1.5, 3.3.2, 3.4.3 |
| Nhập môn Trí tuệ nhân tạo | Phát hiện bất thường không giám sát, đường cơ sở, ngưỡng | 1.1.3, 3.3.8 |
| Lập trình hướng đối tượng | Tách tầng dịch vụ, một hàm chuẩn hóa duy nhất cho một khái niệm | 3.3.5 |
| Mạng máy tính | HTTP, cookie phiên, phi trạng thái, lưu đệm | 1.1.6, 3.3.3 |
| Toán rời rạc | Độ phức tạp, lớp NP-khó | 1.1.1, 1.1.4 |

### 4.3.3. Khoảng trống kiến thức

Ba nội dung mà đợt thực tập cho thấy còn thiếu:

**Lập trình đồng thời và mô hình khóa của hệ quản trị cơ sở dữ liệu.** Môn Cơ sở dữ liệu dạy ACID ở mức tính chất, không dạy hệ quả vận hành: một giao dịch giữ khóa bao lâu, khóa đó chặn ai, và điều gì xảy ra khi hết thời gian chờ. Lỗi ở mục 3.4.3 là hệ quả trực tiếp của khoảng trống này.

**Kiểm thử phần mềm.** Đây là kỹ năng em phải tự học hoàn toàn trong đợt thực tập, và là kỹ năng có tác động lớn nhất đến chất lượng công việc.

**Chất lượng dữ liệu.** Mọi bài tập trong chương trình đều dùng dữ liệu sạch. Bảng 3.6 và Bảng 3.13 là loại vấn đề chiếm phần lớn thời gian thực tế nhưng không xuất hiện trong bài tập nào.

### 4.3.4. Kỹ năng được nâng cao và sự hỗ trợ nhận được

Kỹ năng được nâng cao rõ nhất là **kiểm chứng thay vì tin**. Ba lần trong đợt thực tập, một điều được ghi trong tài liệu hóa ra sai khi đo lại: chẩn đoán về WAL (mục 3.4.3), giả định rằng bản chạy thật và bản phát triển phục vụ cùng một tập tuyến đường (ngày 07/8, thực tế bản chạy thật thiếu 14 tuyến trong đó có cả trang chủ), và giả định rằng số điện thoại sai là do người nhập (ngày 15/8, thực tế do định dạng ô). Cả ba lần, cách phát hiện đều giống nhau: đo lại thay vì đọc lại.

Sự hỗ trợ từ người hướng dẫn tại đơn vị chủ yếu ở phần nghiệp vụ — giải thích vì sao một quy định tồn tại, và phản hồi nhanh khi một tính năng không dùng được trong thực tế. Quyết định gỡ bỏ cơ chế tự động chuyển pha (mục 3.4.3) đến từ phản hồi của bộ phận chứ không từ phân tích kỹ thuật của em.

[[CẦN SỐ LIỆU: sự hỗ trợ từ giảng viên hướng dẫn — nêu cụ thể nội dung đã được góp ý và thời điểm]]

# KẾT LUẬN VÀ KIẾN NGHỊ

## Kết luận

Đợt thực tập tại Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung đã hoàn thành bốn mục tiêu đặt ra ở mục 2 phần Mở đầu: quy trình điều vận được ghi lại thành sơ đồ, bốn điểm nghẽn dữ liệu được xác định và diễn đạt thành bài toán kỹ thuật, hệ thống Fleet Fuel Management được xây dựng và đang chạy trên môi trường thật, và kết quả được kiểm chứng bằng 737 trường hợp kiểm thử tự động cùng dữ liệu vận hành của 14 ngày kế hoạch.

Kết quả cụ thể: 243 điểm dừng có trạng thái thực thi được lưu vết, 3 333 ảnh giao nhận chuyển từ Zalo vào cơ sở dữ liệu có thể tra cứu theo chuyến, 323 phiếu nhiên liệu được kiểm tra bất thường tự động theo đường cơ sở riêng của từng xe, và kế hoạch giao hàng được đọc trực tiếp từ bảng tính của quản lý thay vì chép tay.

Phần chưa đạt cũng rõ ràng như phần đạt được. Cơ chế tự động chuyển pha bằng hàng rào địa lý — mục tiêu em kỳ vọng nhất — đã bị gỡ bỏ vì nó giải sai bài toán: xe đi ngang qua kho không đồng nghĩa với việc đã giao xong hàng ở đó. Nhắc bảo dưỡng tự động và phân hệ xếp hàng mới ở mức chạy được, chưa gắn vào vận hành. Chế độ ghi trước của cơ sở dữ liệu và việc chạy nhiều tiến trình song song đã được đo và có khuyến nghị nhưng chưa triển khai.

Bài học lớn nhất không phải về một thuật toán cụ thể mà về thứ tự làm việc: đo trước khi kết luận, và ghi lại phép đo kể cả khi nó bác bỏ điều mình đã viết. Ba lần trong đợt thực tập, một điều tưởng đã đúng hóa ra sai, và cả ba lần đều được phát hiện bằng cách đo lại chứ không bằng cách đọc lại.

## Kiến nghị

**Kiến nghị 1 — Chuẩn hóa định dạng nguồn dữ liệu.** Đặt cột số điện thoại, cột tọa độ và cột ngày trong bảng kế hoạch về định dạng văn bản. Thao tác này mất vài giây và loại bỏ lớp lỗi đã làm hỏng 118 trên 149 số điện thoại điểm giao.

**Kiến nghị 2 — Bổ sung dữ liệu kỹ thuật phương tiện từ giấy đăng kiểm.** Nhập chiều cao, chiều rộng, tổng tải trọng và tải trọng trục thật của từng xe thay cho giá trị mặc định theo loại. Đây là điều kiện để định tuyến theo ràng buộc phương tiện cho kết quả đúng ở mức từng xe.

**Kiến nghị 3 — Bật chế độ ghi trước và giải quyết trạng thái dùng chung trước khi tăng số tiến trình xử lý.** Phép đo ở Bảng 3.10 cho thấy lợi ích về thông lượng, nhưng thứ tự phải đúng: chuyển bộ nhớ đệm và các khóa ra khỏi bộ nhớ tiến trình trước, rồi mới tăng số tiến trình.

**Kiến nghị 4 — Đo hiện trạng trước mỗi lần số hóa tiếp theo.** Ghi lại số phút, số lần nhập liệu, số lần phải hỏi lại của quy trình hiện tại trước khi thay đổi nó. Không có mốc so sánh là lý do đợt này không thể khẳng định hiệu quả của việc số hóa chứng từ giao nhận bằng con số.

**Kiến nghị 5 — Xem lại quyết định không có xác thực nếu phạm vi truy cập thay đổi.** Quyết định hiện tại phù hợp với điều kiện mạng nội bộ. Nếu hệ thống được mở ra internet hoặc tài xế truy cập từ điện thoại cá nhân, đây là việc phải bàn trước khi thêm bất kỳ tính năng nào.

# TÀI LIỆU THAM KHẢO

## Tài liệu khoa học

[2] G. B. Dantzig and J. H. Ramser, "The truck dispatching problem," *Management Science*, vol. 6, no. 1, pp. 80–91, 1959, doi: 10.1287/mnsc.6.1.80.

[3] P. Toth and D. Vigo, Eds., *Vehicle Routing: Problems, Methods, and Applications*, 2nd ed., MOS-SIAM Series on Optimization, no. 18. Philadelphia, PA: SIAM, 2014.

[4] F. Reclus and K. Drouard, "Geofencing for fleet & freight management," in *Proc. 9th Int. Conf. Intelligent Transport Systems Telecommunications (ITST)*, Lille, France, 2009, pp. 353–356.

[5] K. Hormann and A. Agathos, "The point in polygon problem for arbitrary polygons," *Computational Geometry: Theory and Applications*, vol. 20, no. 3, pp. 131–144, 2001, doi: 10.1016/S0925-7721(01)00012-8.

[6] R. W. Sinnott, "Virtues of the haversine," *Sky and Telescope*, vol. 68, no. 2, pp. 158–159, 1984.

[7] V. Chandola, A. Banerjee, and V. Kumar, "Anomaly detection: A survey," *ACM Computing Surveys*, vol. 41, no. 3, art. 15, pp. 1–58, 2009, doi: 10.1145/1541880.1541882.

[8] S. W. Roberts, "Control chart tests based on geometric moving averages," *Technometrics*, vol. 1, no. 3, pp. 239–250, 1959, doi: 10.1080/00401706.1959.10489860.

[9] A. Barbado and Ó. Corcho, "Interpretable machine learning models for predicting and explaining vehicle fuel consumption anomalies," *Engineering Applications of Artificial Intelligence*, vol. 115, art. 105222, 2022, doi: 10.1016/j.engappai.2022.105222.

[10] A. Bortfeldt and G. Wäscher, "Constraints in container loading — A state-of-the-art review," *European Journal of Operational Research*, vol. 229, no. 1, pp. 1–20, 2013, doi: 10.1016/j.ejor.2012.12.006.

[11] E. F. Codd, "A relational model of data for large shared data banks," *Communications of the ACM*, vol. 13, no. 6, pp. 377–387, 1970, doi: 10.1145/362384.362685.

[12] R. T. Fielding, "Architectural styles and the design of network-based software architectures," Ph.D. dissertation, Univ. California, Irvine, CA, 2000.

## Tài liệu kỹ thuật, tiêu chuẩn và tài liệu của đơn vị

[1] Chính phủ Việt Nam, *Chiến lược phát triển dịch vụ logistics Việt Nam thời kỳ 2025–2035, tầm nhìn đến năm 2050*. Hà Nội, Việt Nam, 2025. [[CẦN SỐ LIỆU: số hiệu quyết định và ngày ban hành — tra trên Cổng thông tin điện tử Chính phủ trước khi nộp]]

[13] Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung, *Quy trình vận hành và điều độ logistics*, tài liệu nội bộ, 2026.

[14] Pallets Projects. "Flask documentation." flask.palletsprojects.com. https://flask.palletsprojects.com/ (truy cập 16/8/2026).

[15] SQLite Consortium. "SQLite documentation." sqlite.org. https://www.sqlite.org/docs.html (truy cập 16/8/2026).

[16] HeiGIT. "OpenRouteService API documentation." openrouteservice.org. https://openrouteservice.org/dev/#/api-docs (truy cập 16/8/2026).

[17] Microsoft. "Playwright for Python." playwright.dev. https://playwright.dev/python/ (truy cập 16/8/2026).

[18] V. Agafonkin. "Leaflet — an open-source JavaScript library for mobile-friendly interactive maps." leafletjs.com. https://leafletjs.com/ (truy cập 16/8/2026).

[19] Chart.js contributors. "Chart.js documentation." chartjs.org. https://www.chartjs.org/docs/latest/ (truy cập 16/8/2026).

# PHỤ LỤC

## Phụ lục A: Truy vấn nguồn của các số liệu trong báo cáo

Toàn bộ truy vấn dưới đây chạy trên tệp `routing_system.db` ngày 16/8/2026. Kết quả ghi kèm để đối chiếu với các bảng trong phần thân báo cáo.

### A.1. Đội xe (Bảng 2.4)

```sql
SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type;
-- 2.5 Tons 15 | 5 Tons 5 | Container 4 | 10 Tons 4 | 1.5 Tons 4 | 9 Tons 2 | 8 Tons 2
SELECT COUNT(*) FROM vehicles;               -- 36
SELECT plate_number FROM vehicles ORDER BY plate_number;  -- 36 dòng, sê-ri 50E/50F/50H/51C/51D
```

### A.2. Nhiên liệu (Bảng 2.6, Bảng 3.11)

```sql
SELECT COUNT(*), MIN(log_date), MAX(log_date) FROM fuel_log;
-- 323 | 2026-06-23 | 2026-07-28
SELECT COUNT(DISTINCT license_plate) FROM fuel_log;          -- 31
SELECT ROUND(SUM(liters),1) FROM fuel_log;                   -- 19967.2
SELECT ROUND(SUM(liters*unit_price)) FROM fuel_log WHERE unit_price IS NOT NULL;
-- 452679427
SELECT COUNT(*) FROM fuel_log
 WHERE old_km IS NOT NULL AND new_km IS NOT NULL AND new_km > old_km;   -- 319
SELECT COUNT(*) FROM fuel_log
 WHERE old_km IS NULL OR new_km IS NULL OR new_km <= old_km;            -- 4
SELECT COUNT(*) FROM fuel_vehicle_profile;                              -- 2
```

### A.3. Giao hàng (Bảng 2.5, Bảng 3.12)

```sql
SELECT COUNT(*), MIN(plan_date), MAX(plan_date) FROM delivery_plans;
-- 14 | 2026-08-01 | 2026-08-16
SELECT COUNT(*) FROM vehicle_assignments;                    -- 62
SELECT ROUND(AVG(n),1), MIN(n), MAX(n)
  FROM (SELECT COUNT(*) n FROM vehicle_assignments GROUP BY plan_id);   -- 4.4 | 3 | 6
SELECT COUNT(*) FROM delivery_plan_stops;                    -- 243
SELECT COUNT(DISTINCT station_name) FROM delivery_plan_stops;-- 241
SELECT ROUND(AVG(n),1), MIN(n), MAX(n)
  FROM (SELECT COUNT(*) n FROM delivery_plan_stops GROUP BY vehicle_assignment_id);
-- 3.9 | 2 | 5
SELECT status, COUNT(*) FROM stop_executions GROUP BY status;
-- cancelled 2 | completed 224 | planned 17
SELECT COUNT(*) FROM stop_status_events;                     -- 472
SELECT COUNT(*) FROM delivery_stop_images;                   -- 3333
SELECT COUNT(DISTINCT stop_id) FROM delivery_stop_images;    -- 105
SELECT ROUND(AVG(c),1)
  FROM (SELECT COUNT(*) c FROM delivery_stop_images GROUP BY stop_id);  -- 31.7
SELECT ROUND(MIN(lat),3), ROUND(MAX(lat),3), ROUND(MIN(lng),3), ROUND(MAX(lng),3)
  FROM delivery_plan_stops WHERE lat IS NOT NULL;
-- 8.966 | 10.903 | 104.558 | 106.69
```

### A.4. Bảo dưỡng, xếp hàng, đồng bộ (Bảng 3.8)

```sql
SELECT COUNT(*), MIN(log_date), MAX(log_date) FROM oil_km_log;  -- 1 | 2026-07-23 | 2026-07-23
SELECT COUNT(*) FROM tlp_load_plans;                            -- 18
SELECT COUNT(*) FROM tlp_shipments;                             -- 1
SELECT COUNT(*) FROM container_configs;                         -- 35
SELECT COUNT(*) FROM sync_history;                              -- 22
SELECT COUNT(*) FROM drivers;                                   -- 2
```

### A.5. Quy mô mã nguồn và kiểm thử (Bảng 3.2, Bảng 3.3, Bảng 3.9)

```bash
find app services truck_load_planner -name "*.py" | xargs wc -l | tail -1   # 16064
find static/js -name "*.js" | xargs wc -l | tail -1                         # 14364
grep -cE "\.route\(" app/routes/*.py services/delivery/routes.py \
     truck_load_planner/routes.py                                           # tổng 130
python3 -m pytest tests/ -q                                                 # 737 passed in 71.21s
grep -cE "^\s*(test|it)\(" tests/js/*.js                                    # tổng 241 (đếm tĩnh)
```

## Phụ lục B: Lược đồ các bảng chính

Cơ sở dữ liệu gồm 25 bảng. Dưới đây là các bảng được nhắc đến trong phần thân báo cáo.

### B.1. `vehicles` — danh mục phương tiện

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | INTEGER PK | Khóa chính |
| `plate_number` | TEXT UNIQUE | Biển số, dạng chính tắc |
| `vehicle_type` | TEXT | Loại xe, dùng để chọn ngưỡng bất thường và cấu hình thùng |
| `current_driver` | TEXT | Tài xế hiện tại |
| `created_at`, `updated_at` | TIMESTAMP | Dấu thời gian |

### B.2. `fuel_log` — nhật ký đổ nhiên liệu

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | INTEGER PK | Khóa chính |
| `license_plate` | TEXT NOT NULL | Biển số |
| `log_date`, `log_time` | TEXT | Ngày, giờ đổ |
| `gas_store` | TEXT | Cây xăng |
| `old_km`, `new_km` | REAL | Số km cũ, mới — thiếu thì không tính được lít/100 km |
| `liters` | REAL | Số lít |
| `unit_price` | REAL | Đơn giá VND/lít |
| `driver_name` | TEXT | Tài xế |
| `is_full_tank` | INTEGER | Cờ đổ đầy bình |
| `notes` | TEXT | Ghi chú |
| `vehicle_id` | INTEGER | Khóa ngoại tới `vehicles` |

### B.3. `delivery_plan_stops` — điểm dừng theo kế hoạch

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | INTEGER PK | Khóa chính |
| `vehicle_assignment_id` | INTEGER | Khóa ngoại tới `vehicle_assignments` |
| `planned_sequence` | INTEGER | Thứ tự dừng theo kế hoạch |
| `station_code`, `station_name` | TEXT | Mã và tên điểm giao |
| `address` | TEXT | Địa chỉ, dạng chuỗi tự do |
| `lat`, `lng` | REAL | Tọa độ, sau khi qua bộ phân tích ở mục 3.3.7 |
| `manager_name`, `manager_phone` | TEXT | Người phụ trách điểm giao |
| `product_description`, `note` | TEXT | Mô tả hàng, ghi chú |

### B.4. `stop_executions` — trạng thái thực thi

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | INTEGER PK | Khóa chính |
| `stop_id` | INTEGER | Khóa ngoại tới `delivery_plan_stops` |
| `execution_sequence` | INTEGER | Thứ tự thực tế, có thể khác thứ tự kế hoạch |
| `status` | TEXT | `planned` · `completed` · `cancelled` |
| `skip_reason`, `cancel_reason` | TEXT | Lý do bỏ qua, lý do hủy |
| `actual_arrival_at`, `actual_departure_at`, `completed_at` | TIMESTAMP | Mốc thời gian thực tế |

### B.5. `oil_km_log` — nhật ký số km bảo dưỡng

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | INTEGER PK | Khóa chính |
| `license_plate` | TEXT NOT NULL | Biển số |
| `log_date` | TEXT NOT NULL | Ngày ghi nhận |
| `km` | INTEGER | Số km đọc từ TTAS |
| `fetched_at` | TIMESTAMP | Thời điểm đồng bộ |
| | UNIQUE(`license_plate`, `log_date`) | Ràng buộc chống trùng, xem mục 1.1.5 |

## Phụ lục C: Ảnh chụp màn hình hệ thống

[[CHO TRONG: Hình C.1. Bảng điều khiển điều độ — bản đồ, danh sách xe, khung thời gian điểm dừng]]

[[CHO TRONG: Hình C.2. Trang hiệu suất nhiên liệu — biểu đồ theo thời gian với các điểm bất thường được đánh dấu]]

[[CHO TRONG: Hình C.3. Trình dựng kế hoạch giao hàng — bước nhập từ Google Sheet kèm danh sách cảnh báo]]

[[CHO TRONG: Hình C.4. Trang bảo dưỡng — tiến độ theo chu kỳ km của từng xe]]

[[CHO TRONG: Hình C.5. Phân hệ xếp hàng — phương án xếp trong thùng xe 2,5 tấn, chế độ xem ba chiều]]

[[CHO TRONG: Hình C.6. Trình soạn vùng địa lý — vẽ đa đa giác cho một kho có hai cổng vào]]

## Phụ lục D: Chứng từ và biểu mẫu thực tế

[[CHO TRONG: Hình D.1. Bảng tổng hợp booking hằng ngày (bản photo, đã che thông tin khách hàng)]]

[[CHO TRONG: Hình D.2. Biên bản sự cố chậm giao hàng (bản photo, đã che thông tin khách hàng)]]

[[CHO TRONG: Hình D.3. Một trang nhật ký nhiên liệu trên Excel trước khi số hóa]]

[[CẦN SỐ LIỆU: xin phép người hướng dẫn tại đơn vị trước khi đính kèm bất kỳ chứng từ nào ở Phụ lục D; che tên khách hàng, số điện thoại và giá cước]]
