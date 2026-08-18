# CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN

Chương này trình bày cơ sở lý thuyết ngành Khoa học Máy tính được vận dụng để giải quyết bài toán nêu ở phần Mở đầu, giới thiệu chủ đề kiến tập dưới dạng một phát biểu bài toán kỹ thuật, và xác định các tiêu chí đo được để đánh giá kết quả. Bối cảnh nghiệp vụ và quy mô doanh nghiệp làm phát sinh các ràng buộc kỹ thuật ở đây được mô tả tại Chương 2; phần triển khai từng lý thuyết thành mã nguồn và kết quả đo đạc được trình bày tại Chương 3.

## 1.1. Tổng quan cơ sở lý thuyết

Hệ thống Fleet Fuel Management được xây dựng trong đợt kiến tập là một ứng dụng web quản lý đội xe, tính đến thời điểm viết báo cáo gồm 16.064 dòng mã Python và 14.364 dòng mã JavaScript, phục vụ 36 phương tiện đang khai thác.

<!-- nguồn: find app truck_load_planner services -name "*.py" | xargs wc -l → 16064; find static -name "*.js" | xargs wc -l → 14364; chạy 2026-08-17 -->
<!-- nguồn: SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type trên routing_system.db → 36 xe, chạy 2026-08-17 -->

Việc xây dựng hệ thống đòi hỏi vận dụng năm nhóm kiến thức: kiến trúc ứng dụng web, mô hình dữ liệu quan hệ, hình học tính toán trên dữ liệu định vị, các bài toán tối ưu tổ hợp trong vận tải, và tiền xử lý dữ liệu kèm phát hiện bất thường. Bảng 1.1 ánh xạ từng nhóm sang học phần trong chương trình đào tạo và sang mục cụ thể ở Chương 3 nơi kiến thức đó được áp dụng.

**Bảng 1.1. Ánh xạ học phần — cơ sở lý thuyết — mục áp dụng**

| Học phần | Cơ sở lý thuyết vận dụng | Mục trình bày ở Chương 3 |
|---|---|---|
| Lập trình hướng đối tượng, Công nghệ phần mềm | Kiến trúc phân lớp, phong cách REST, tách module | 3.4.1 |
| Cơ sở dữ liệu | Mô hình quan hệ, chuẩn hóa, ràng buộc toàn vẹn, SQL | 3.4.2 |
| Cấu trúc dữ liệu và giải thuật, Đồ họa máy tính | Hình học tính toán: điểm-trong-đa-giác, khoảng cách trên mặt cầu | 3.4.3 |
| Trí tuệ nhân tạo, Tối ưu hóa | VRP, bài toán xếp thùng ba chiều, heuristic tham lam | 3.4.4 |
| Nhập môn Khoa học dữ liệu, Học máy | Làm sạch dữ liệu, phát hiện điểm bất thường | 3.5 |

### 1.1.1. Kiến trúc ứng dụng web phân lớp và phong cách REST

Ứng dụng web hiện đại thường được tổ chức theo kiến trúc client–server phân lớp, trong đó tầng trình bày, tầng xử lý nghiệp vụ và tầng lưu trữ tách biệt nhau, mỗi tầng chỉ giao tiếp với tầng liền kề. Fielding [10] hệ thống hóa cách tổ chức này thành phong cách kiến trúc REST (Representational State Transfer), với các ràng buộc: giao tiếp không trạng thái, giao diện đồng nhất, phân lớp và khả năng lưu đệm. Trong REST, mỗi tài nguyên được định danh bằng một URI, và các phương thức HTTP (GET, POST, PUT, DELETE) biểu diễn thao tác trên tài nguyên đó.

Ràng buộc không trạng thái có hệ quả trực tiếp lên thiết kế: máy chủ không lưu ngữ cảnh của phiên làm việc giữa hai yêu cầu, nên mọi thông tin cần thiết phải nằm trong bản thân yêu cầu. Điều này giúp việc mở rộng theo chiều ngang trở nên khả thi, nhưng buộc trạng thái dùng chung, chẳng hạn bộ nhớ đệm dữ liệu lộ trình, phải được xử lý tường minh thay vì ẩn trong phiên.

Hệ thống được cài đặt bằng Flask, một micro-framework Python tuân theo giao diện WSGI. Flask cung cấp cơ chế Blueprint cho phép nhóm các tuyến đường theo miền nghiệp vụ và đăng ký chúng vào một nhà máy tạo ứng dụng duy nhất. Kiến trúc ba lớp của hệ thống được minh họa ở Hình 1.1.

![Hình 1.1. Kiến trúc ba lớp của hệ thống Fleet Fuel Management](placeholder)

Các công nghệ được sử dụng, cùng vai trò của từng thành phần, được liệt kê ở Bảng 1.2.

**Bảng 1.2. Công nghệ sử dụng trong hệ thống**

<!-- nguồn: requirements.txt (mã hóa UTF-16), đọc 2026-08-17 -->

| Thành phần | Công nghệ | Phiên bản | Vai trò |
|---|---|---|---|
| Web framework | Flask | 3.1.3 | Định tuyến, kết xuất giao diện, tầng API |
| Máy chủ WSGI | Gunicorn | 26.0.0 | Phục vụ ứng dụng trên môi trường triển khai |
| Cơ sở dữ liệu | SQLite | (nhúng trong Python) | Lưu trữ toàn bộ dữ liệu nghiệp vụ |
| Bản đồ nền | Leaflet | (thư viện phía trình duyệt) | Hiển thị vị trí phương tiện và lộ trình |
| Dịch vụ định tuyến | OpenRouteService | (API ngoài) | Tính lộ trình theo hồ sơ xe tải nặng |
| Xếp hàng ba chiều | py3dbp | 1.1.2 | Thư viện tham chiếu cho bài toán xếp thùng |
| Xử lý bảng biểu | pandas, openpyxl | 2.3.3 / 3.1.5 | Nhập và xuất dữ liệu dạng bảng |
| Bóc tách dữ liệu web | BeautifulSoup | 4.15.0 | Đọc dữ liệu giám sát hành trình từ hệ thống TTAS |
| Kiểm thử | pytest, Playwright | 9.1.1 / 1.61.0 | Kiểm thử tầng dịch vụ và tầng tuyến đường |

Toàn bộ tầng API hiện gồm 130 điểm cuối, phân bố trên 7 Blueprint theo miền nghiệp vụ: `core`, `fleet`, `fuel`, `oil`, `trips`, `tlp` và `delivery`.

<!-- nguồn: grep -rEn "@[a-z_]+\.route\(" trên app/, truck_load_planner/, services/ → 130; grep "Blueprint(" → 7; chạy 2026-08-17 -->

Cách phân rã này được áp dụng cụ thể ở mục 3.4.1.

### 1.1.2. Mô hình dữ liệu quan hệ và ngôn ngữ truy vấn SQL

Mô hình dữ liệu quan hệ do Codd [9] đề xuất năm 1970 biểu diễn dữ liệu bằng các quan hệ, tức các bảng gồm hàng và cột, tách biệt hoàn toàn cấu trúc logic của dữ liệu khỏi cách lưu trữ vật lý. Người dùng truy xuất dữ liệu bằng một ngôn ngữ phi thủ tục, mô tả kết quả cần lấy chứ không mô tả đường đi để lấy nó. Mô hình này là nền tảng của SQL và của phần lớn hệ quản trị cơ sở dữ liệu đang được dùng trong doanh nghiệp.

Ba khái niệm được vận dụng trực tiếp khi thiết kế lược đồ dữ liệu của hệ thống:

- **Khóa chính và khóa ngoại.** Khóa chính định danh duy nhất một bộ trong quan hệ; khóa ngoại tham chiếu tới khóa chính của quan hệ khác, tạo nên ràng buộc toàn vẹn tham chiếu. Trong hệ thống, biển số xe được dùng làm khóa nghiệp vụ nối các bảng phương tiện, nhật ký nhiên liệu, lịch bảo dưỡng và phân công chuyến.
- **Chuẩn hóa.** Việc tách dữ liệu thành nhiều quan hệ nhằm loại bỏ dư thừa và các bất thường khi thêm, sửa, xóa. Chẳng hạn, thông số kỹ thuật theo loại xe được tách khỏi bảng phương tiện thành một quan hệ riêng, tránh lặp lại cùng một bộ thông số trên mọi xe cùng loại.
- **Giao dịch.** Một nhóm thao tác ghi được thực hiện trọn vẹn hoặc không thực hiện gì. SQLite tuần tự hóa các giao dịch ghi, nên một giao dịch giữ khóa ghi quá lâu sẽ khiến các yêu cầu ghi khác thất bại — ràng buộc này ảnh hưởng trực tiếp tới cách tổ chức luồng đồng bộ dữ liệu, được phân tích ở mục 3.4.2.

Hệ thống sử dụng SQLite, một hệ quản trị cơ sở dữ liệu nhúng lưu toàn bộ dữ liệu trong một tệp duy nhất, không cần tiến trình máy chủ riêng. Lược đồ hiện gồm 25 bảng. Quy mô dữ liệu tại thời điểm khảo sát được trình bày ở Bảng 1.3.

**Bảng 1.3. Quy mô dữ liệu của hệ thống**

<!-- nguồn: SELECT COUNT(*) trên từng bảng của routing_system.db, chạy 2026-08-17 -->

| Nhóm dữ liệu | Bảng tiêu biểu | Số bản ghi |
|---|---|---|
| Phương tiện | `vehicles` | 36 |
| Loại phương tiện | `vehicle_types` | 7 |
| Nhật ký nhiên liệu | `fuel_log` | 323 |
| Kế hoạch giao hàng | `delivery_plans` | 15 |
| Điểm dừng trong kế hoạch | `delivery_plan_stops` | 258 |
| Lịch sử thực hiện điểm dừng | `stop_status_events` | 534 |
| Ảnh chứng từ giao hàng | `delivery_stop_images` | 4.210 |
| Vị trí xếp hàng đã tính | `tlp_placements` | 138 |
| Phân công xe | `vehicle_assignments` | 66 |

Cơ cấu 36 phương tiện theo tải trọng gồm: 15 xe 2,5 tấn; 5 xe 5 tấn; 4 xe 1,5 tấn; 4 xe 10 tấn; 4 xe container; 2 xe 8 tấn và 2 xe 9 tấn.

<!-- nguồn: SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type, chạy 2026-08-17 -->

### 1.1.3. Định vị vệ tinh, khoảng cách trên mặt cầu và hàng rào địa lý

Dữ liệu hành trình của đội xe được thu thập từ thiết bị giám sát hành trình gắn trên xe, trả về tọa độ địa lý dưới dạng cặp vĩ độ và kinh độ. Hai bài toán hình học phát sinh từ dữ liệu này.

**Khoảng cách giữa hai điểm trên mặt cầu.** Do Trái Đất không phẳng, khoảng cách giữa hai tọa độ không tính được bằng định lý Pythagoras. Công thức haversine, được Sinnott [8] phổ biến, tính khoảng cách vòng lớn với độ ổn định số cao ngay cả khi hai điểm rất gần nhau — điều mà công thức cosin cầu không bảo đảm do sai số làm tròn. Với hai điểm có vĩ độ φ₁, φ₂ và chênh lệch kinh độ Δλ, khoảng cách d trên mặt cầu bán kính R được tính bằng:

a = sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)

d = 2R · atan2(√a, √(1−a))

Hệ thống cài đặt công thức này với R = 6.371.000 m.

<!-- nguồn: app/utils/geo.py, hàm get_distance_meters, hằng R = 6371000, đọc 2026-08-17 -->

**Xác định phương tiện có nằm trong một khu vực hay không.** Đây là bài toán điểm-trong-đa-giác, một trong những bài toán cơ bản của hình học tính toán. Thuật toán ray casting do Shimrat [5] công bố năm 1962 giải bài toán này bằng cách bắn một tia từ điểm cần kiểm tra theo một hướng bất kỳ và đếm số lần tia cắt biên đa giác: số lần cắt lẻ nghĩa là điểm nằm trong, số chẵn nghĩa là điểm nằm ngoài. Thuật toán có độ phức tạp O(n) với n là số đỉnh của đa giác, không yêu cầu đa giác lồi và không cần tiền xử lý. Haines [6] so sánh các biến thể và chỉ ra rằng với đa giác ít đỉnh và truy vấn thưa, ray casting vẫn là lựa chọn hợp lý so với các phương pháp cần dựng cấu trúc dữ liệu phụ trợ.

![Hình 1.2. Nguyên lý thuật toán ray casting trong kiểm tra điểm thuộc đa giác](placeholder)

Khi áp dụng vào quản lý vận tải, kỹ thuật này mang tên geofencing: một khu vực được định nghĩa bằng đa giác tọa độ, hệ thống kiểm tra định kỳ vị trí phương tiện và phát sinh sự kiện khi xe vào hoặc rời khu vực. Reclus và Drouard [7] trình bày các ứng dụng của geofencing trong quản lý đội xe và vận tải hàng hóa, gồm giám sát thời gian lưu bãi, kiểm soát tuyến và cảnh báo lệch lộ trình. Cách hệ thống áp dụng hai thuật toán trên được trình bày ở mục 3.4.3.

### 1.1.4. Bài toán định tuyến phương tiện và bài toán xếp hàng ba chiều

Hai bài toán tối ưu tổ hợp cổ điển nằm ở lõi của nghiệp vụ điều phối vận tải.

**Bài toán định tuyến phương tiện (Vehicle Routing Problem — VRP)** được Dantzig và Ramser [1] phát biểu lần đầu năm 1959 dưới tên bài toán điều phối xe bồn: xác định tập lộ trình có tổng chi phí nhỏ nhất cho một đội xe xuất phát từ kho, phục vụ một tập điểm giao hàng có nhu cầu xác định, sao cho mỗi điểm được phục vụ đúng một lần và tải trọng mỗi xe không vượt sức chứa. VRP là tổng quát hóa của bài toán người bán hàng rong và thuộc lớp NP-khó, nghĩa là chưa tồn tại thuật toán giải chính xác trong thời gian đa thức. Toth và Vigo [2] tổng hợp các biến thể của bài toán cùng các phương pháp giải chính xác và heuristic.

Trong phạm vi đợt kiến tập, hệ thống không giải VRP ở dạng tối ưu toàn cục. Thứ tự các điểm dừng do điều phối viên quyết định dựa trên kinh nghiệm và yêu cầu của khách hàng; hệ thống đảm nhận phần tính lộ trình và thời gian di chuyển giữa các điểm liên tiếp thông qua dịch vụ OpenRouteService với hồ sơ `driving-hgv` dành cho xe tải nặng. Đây là ranh giới cần nêu rõ: hệ thống hỗ trợ ra quyết định về lộ trình, không thay thế quyết định đó.

<!-- nguồn: app/services/routing.py, DEFAULT_PROFILE = "driving-hgv", đọc 2026-08-17 -->

**Bài toán xếp thùng ba chiều (Three-Dimensional Bin Packing Problem — 3D-BPP)** yêu cầu xếp một tập hộp chữ nhật vào số thùng chứa ít nhất, sao cho các hộp không chồng lấn nhau và nằm trọn trong thùng. Martello, Pisinger và Vigo [3] chứng minh bài toán này là NP-khó theo nghĩa mạnh và đề xuất thuật toán nhánh cận cho bài toán chính xác. Với quy mô thực tế của doanh nghiệp, lời giải chính xác không khả thi về thời gian, nên hệ thống sử dụng heuristic.

Phân hệ xếp hàng của hệ thống áp dụng ba kỹ thuật:

- **Biểu diễn hình học bằng hộp bao căn trục (AABB).** Mỗi kiện hàng và mỗi khoang chứa được biểu diễn bằng một hộp có các cạnh song song với trục tọa độ. Kiểm tra va chạm giữa hai AABB chỉ cần so sánh khoảng chiếu trên ba trục, độ phức tạp O(1) mỗi cặp. Ericson [4] trình bày chi tiết các phép kiểm tra giao cắt và các cấu trúc phân hoạch không gian dùng để giảm số cặp cần kiểm tra.
- **Heuristic xếp phần tử lớn trước.** Các kiện hàng được sắp giảm dần theo thể tích rồi lần lượt đặt vào vị trí khả thi đầu tiên. Đây là biến thể của họ heuristic first-fit decreasing, cho lời giải chấp nhận được trong thời gian đa thức.
- **Hàm điểm đa tiêu chí.** Mỗi vị trí ứng viên được chấm điểm theo sáu tiêu chí có trọng số khác nhau, phản ánh các yêu cầu thực tế của việc xếp hàng lên xe tải. Bảng 1.4 trình bày bộ trọng số hiện dùng.

**Bảng 1.4. Trọng số các tiêu chí trong hàm chấm điểm vị trí xếp hàng**

<!-- nguồn: truck_load_planner/engine/scorer.py, hằng SCORING_WEIGHTS, đọc 2026-08-17 -->

| Tiêu chí | Trọng số | Ý nghĩa |
|---|---|---|
| `contact_area` | 1000 | Diện tích tiếp xúc với mặt sàn và các kiện lân cận |
| `x_position` | 200 | Mức độ hoàn chỉnh của lớp hàng theo chiều dọc thùng xe |
| `weight_balance` | 50 | Cân bằng trọng lượng theo trục ngang |
| `usable_space` | 3 | Phạt các vị trí tạo ra khoảng trống không dùng được |
| `stack_level` | 1 | Số lớp chồng |
| `tower_height` | 1 | Chiều cao cột hàng |

Trọng số không đồng đều phản ánh thứ tự ưu tiên: một vị trí có diện tích tiếp xúc lớn nhưng tạo ra khoảng trống chết vẫn bị loại, do khoản phạt của tiêu chí `usable_space` được nhân hệ số đủ lớn để vượt qua điểm tiếp xúc tối đa. Chi tiết cài đặt và kết quả kiểm thử của phân hệ này được trình bày ở mục 3.4.4.

### 1.1.5. Tiền xử lý dữ liệu và phát hiện bất thường trong tiêu hao nhiên liệu

Dữ liệu vận hành của doanh nghiệp đến từ nhiều nguồn với mức độ chuẩn hóa khác nhau: bảng tính do nhân viên nhập tay, dữ liệu bóc tách từ hệ thống giám sát hành trình, và dữ liệu nhập trực tiếp trên giao diện. Trước khi đưa vào tính toán, dữ liệu cần qua các bước kiểm tra tính đầy đủ, chuẩn hóa định dạng và loại bỏ bản ghi mâu thuẫn. Biển số xe là ví dụ điển hình: cùng một phương tiện có thể xuất hiện dưới nhiều cách viết khác nhau về dấu chấm, dấu gạch ngang và khoảng trắng, nên hệ thống phải chuẩn hóa về một dạng duy nhất trước khi đối chiếu.

Chandola, Banerjee và Kumar [11] phân loại các phương pháp phát hiện bất thường thành ba nhóm theo dữ liệu huấn luyện sẵn có: có giám sát, bán giám sát và không giám sát; đồng thời phân biệt bất thường điểm, bất thường theo ngữ cảnh và bất thường tập thể. Bài toán phát hiện xe có mức tiêu hao nhiên liệu bất thường thuộc dạng bất thường theo ngữ cảnh, vì một mức tiêu hao chỉ bất thường khi so với chính loại xe đó và điều kiện vận hành tương ứng, chứ không so với toàn đội xe.

Hướng tiếp cận bằng học máy đã được nghiên cứu cho xe tải nặng. Katreddi và Thiruvengadam [12] xây dựng mô hình mạng nơ-ron dự báo tiêu hao nhiên liệu theo chuyến dựa trên tải động cơ và tốc độ vòng quay; Katreddi, Kasani và Thiruvengadam [13] tổng hợp các ứng dụng trí tuệ nhân tạo trong lĩnh vực xe tải nặng, gồm dự báo tiêu hao nhiên liệu, ước lượng phát thải và bảo dưỡng dự đoán.

Trong phạm vi đợt kiến tập này, hệ thống chưa xây dựng mô hình học máy. Phương pháp đang dùng là luật ngưỡng dựa trên đường cơ sở tính từ lịch sử của chính phương tiện: một bản ghi bị đánh dấu bất thường khi mức tiêu hao vượt đường cơ sở nhân với hệ số 1,20 đối với xe tải thùng và 1,50 đối với xe container, hoặc khi mức tiêu hao thấp dưới 8 L/100 km — ngưỡng dưới này nhằm bắt lỗi nhập liệu thay vì bắt hành vi vận hành.

<!-- nguồn: app/routes/fuel.py, hàm _get_anomaly_multiplier và _apply_anomaly_flag, đọc 2026-08-17 -->

Lý do chọn luật ngưỡng thay vì mô hình học máy là ràng buộc dữ liệu: bảng nhật ký nhiên liệu hiện có 323 bản ghi, chưa đủ để huấn luyện và đánh giá một mô hình có ý nghĩa thống kê, và cũng chưa có nhãn xác nhận trường hợp nào thực sự bất thường. Việc mở rộng sang mô hình học máy được đề xuất như hướng phát triển tiếp theo ở phần Kết luận và kiến nghị. Cách xây dựng đường cơ sở và kết quả áp dụng luật ngưỡng trên dữ liệu thực được trình bày ở mục 3.5.

## 1.2. Chủ đề thực tập

Chủ đề kiến tập được phát biểu dưới dạng một bài toán kỹ thuật như sau.

**Đầu vào.** Dữ liệu vận hành hằng ngày của một đội xe 36 phương tiện thuộc 7 nhóm tải trọng, gồm: thông tin định danh và thông số kỹ thuật phương tiện; dữ liệu vị trí và trạng thái từ hệ thống giám sát hành trình; nhật ký đổ nhiên liệu và số ki-lô-mét đồng hồ; lịch bảo dưỡng và thay dầu; kế hoạch giao hàng theo ngày cùng danh sách điểm dừng; kích thước và trọng lượng kiện hàng cần xếp lên xe.

**Đầu ra.** Một ứng dụng web nội bộ cho phép nhân viên điều hành: tra cứu tập trung thông tin phương tiện; theo dõi vị trí và tiến độ giao hàng theo thời gian gần thực; thống kê mức tiêu hao nhiên liệu theo xe và theo tháng kèm cảnh báo bất thường; theo dõi lịch bảo dưỡng; và lập phương án xếp hàng ba chiều cho từng chuyến.

**Ràng buộc.** Hệ thống chạy trên mạng nội bộ của doanh nghiệp, được sử dụng bởi nhân viên điều hành trong giờ làm việc, một phần thao tác diễn ra trên thiết bị di động tại hiện trường. Dữ liệu đầu vào không được chuẩn hóa sẵn và tiếp tục được nhập tay song song với hệ thống trong giai đoạn chuyển đổi, nên hệ thống phải chấp nhận dữ liệu thiếu hoặc sai định dạng mà không dừng hoạt động.

Từ phát biểu trên, đề tài được đặt tên: *"Khảo sát quy trình quản lý đội xe và xây dựng hệ thống hỗ trợ quản lý phương tiện, nhiên liệu và bảo dưỡng tại Công ty Cổ phần Thương mại Dịch vụ và Đầu tư Thành Trung."*

Hệ thống được phân rã thành bốn phân hệ, mỗi phân hệ giải một phần của bài toán và dựa trên nhóm lý thuyết tương ứng đã trình bày ở mục 1.1:

1. **Quản lý phương tiện và bảo dưỡng** — mô hình dữ liệu quan hệ (mục 1.1.2).
2. **Quản lý nhiên liệu** — tiền xử lý dữ liệu và phát hiện bất thường (mục 1.1.5).
3. **Giám sát hành trình và điều phối giao hàng** — hình học tính toán trên dữ liệu định vị và dịch vụ định tuyến (mục 1.1.3, 1.1.4).
4. **Lập phương án xếp hàng** — bài toán xếp thùng ba chiều (mục 1.1.4).

Ranh giới phạm vi cần nêu rõ ngay từ đầu: hệ thống không giải bài toán VRP ở dạng tối ưu toàn cục, không xây dựng mô hình học máy dự báo tiêu hao nhiên liệu, và không xử lý các nghiệp vụ kế toán hay quản lý kho. Ba hạng mục này nằm ngoài phạm vi và được ghi nhận ở phần Kết luận như hướng phát triển.

## 1.3. Các kết quả và mục tiêu kỳ vọng

Để tránh đánh giá kết quả bằng nhận định định tính, đợt kiến tập đặt ra các tiêu chí chấp nhận có thể đo được, trình bày ở Bảng 1.5. Kết quả đo thực tế đối chiếu với các tiêu chí này được trình bày ở mục 3.4 và 3.6.

**Bảng 1.5. Tiêu chí chấp nhận của hệ thống**

| Tiêu chí | Cách đo | Mức kỳ vọng |
|---|---|---|
| Đủ bốn phân hệ nghiệp vụ | Đếm phân hệ có giao diện và API hoạt động | 4/4 |
| Dữ liệu thật được nạp vào hệ thống | Đếm bản ghi trong cơ sở dữ liệu | Toàn bộ 36 phương tiện đang khai thác |
| Độ bao phủ kiểm thử tự động | Số ca kiểm thử `pytest` và kiểm thử JavaScript vượt qua | [[CẦN SỐ LIỆU: chạy lại toàn bộ `pytest tests/` và các bộ kiểm thử JavaScript, ghi số ca và thời gian chạy tại thời điểm nộp báo cáo]] |
| Hệ thống chạy được ngoài môi trường phát triển | Triển khai thành công lên máy chủ, truy cập qua trình duyệt | Có |
| Thời gian lập phương án xếp hàng | Đo thời gian phản hồi của API xếp hàng trên một chuyến thực tế | [[CẦN SỐ LIỆU: đo thời gian chạy của thuật toán xếp hàng trên bộ dữ liệu kiện hàng thực tế]] |

Về phía doanh nghiệp, kết quả kỳ vọng là thông tin phương tiện, nhiên liệu và bảo dưỡng được tập trung trên một hệ thống thay vì phân tán trên nhiều tệp bảng tính và các cuộc trao đổi qua ứng dụng nhắn tin, nhờ đó nhân viên điều hành tra cứu được trạng thái đội xe mà không phải tổng hợp thủ công.

Cần nêu rõ một hạn chế về phương pháp đánh giá: doanh nghiệp không ghi nhận số liệu định lượng về thời gian thao tác thủ công trước khi triển khai hệ thống, nên báo cáo này không đưa ra bất kỳ tỷ lệ cải thiện nào. Việc so sánh trước và sau chỉ được trình bày ở dạng mô tả quy trình tại mục 3.3, kèm nhận xét của nhân viên trực tiếp sử dụng.

[[CẦN SỐ LIỆU: nếu xin được số liệu thời gian lập bảng kê thủ công trung bình mỗi ngày từ Phòng Kinh doanh vận tải, bổ sung vào mục 3.6 để có cơ sở so sánh]]

Về phía cá nhân, mục tiêu là trải qua trọn vẹn một chu trình phát triển phần mềm trong môi trường doanh nghiệp: khảo sát yêu cầu từ người dùng thật, thiết kế lược đồ dữ liệu trên nghiệp vụ thật, lựa chọn thuật toán phù hợp với ràng buộc thực tế thay vì với đề bài lý tưởng, kiểm thử và triển khai. Những khác biệt giữa cách làm được học ở trường và cách làm tại doanh nghiệp được phân tích ở mục 4.3.

---

## TÀI LIỆU THAM KHẢO (phần trích dẫn trong Chương 1)

<!-- Toàn bộ 13 tài liệu dưới đây đã được tra cứu và xác minh trực tuyến ngày 2026-08-17: tên tác giả, tên bài, tên tạp chí/kỷ yếu, năm và DOI. Đánh số IEEE theo thứ tự xuất hiện lần đầu trong toàn báo cáo — cần đánh số lại sau khi ghép đủ các chương. -->

[1] G. B. Dantzig and J. H. Ramser, "The truck dispatching problem," *Management Science*, vol. 6, no. 1, pp. 80–91, 1959, doi: 10.1287/mnsc.6.1.80.

[2] P. Toth and D. Vigo, Eds., *Vehicle Routing: Problems, Methods, and Applications*, 2nd ed., MOS-SIAM Series on Optimization, no. 18. Philadelphia, PA: SIAM, 2014.

[3] S. Martello, D. Pisinger, and D. Vigo, "The three-dimensional bin packing problem," *Operations Research*, vol. 48, no. 2, pp. 256–267, 2000, doi: 10.1287/opre.48.2.256.12386.

[4] C. Ericson, *Real-Time Collision Detection*. San Francisco, CA: Morgan Kaufmann, 2004, ISBN 978-1-55860-732-3.

[5] M. Shimrat, "Algorithm 112: Position of point relative to polygon," *Communications of the ACM*, vol. 5, no. 8, p. 434, 1962, doi: 10.1145/368637.368653.

[6] E. Haines, "Point in polygon strategies," in *Graphics Gems IV*, P. S. Heckbert, Ed. San Diego, CA: Academic Press, 1994, pp. 24–46.

[7] F. Reclus and K. Drouard, "Geofencing for fleet & freight management," in *Proc. 9th Int. Conf. Intelligent Transport Systems Telecommunications (ITST)*, Lille, France, 2009, pp. 353–356, doi: 10.1109/ITST.2009.5399328.

[8] R. W. Sinnott, "Virtues of the haversine," *Sky and Telescope*, vol. 68, no. 2, p. 158, 1984.

[9] E. F. Codd, "A relational model of data for large shared data banks," *Communications of the ACM*, vol. 13, no. 6, pp. 377–387, 1970, doi: 10.1145/362384.362685.

[10] R. T. Fielding, "Architectural styles and the design of network-based software architectures," Ph.D. dissertation, Univ. of California, Irvine, CA, 2000.

[11] V. Chandola, A. Banerjee, and V. Kumar, "Anomaly detection: A survey," *ACM Computing Surveys*, vol. 41, no. 3, art. 15, pp. 1–58, 2009, doi: 10.1145/1541880.1541882.

[12] S. Katreddi and A. Thiruvengadam, "Trip based modeling of fuel consumption in modern heavy-duty vehicles using artificial intelligence," *Energies*, vol. 14, no. 24, art. 8592, 2021, doi: 10.3390/en14248592.

[13] S. Katreddi, S. Kasani, and A. Thiruvengadam, "A review of applications of artificial intelligence in heavy duty trucks," *Energies*, vol. 15, no. 20, art. 7457, 2022, doi: 10.3390/en15207457.
