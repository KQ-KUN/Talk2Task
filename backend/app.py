from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import re
from datetime import datetime

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
MEMO_FILE = os.path.join(BASE_DIR, "memo.json")


def load_json_file(file_path, default_value):
    if not os.path.exists(file_path):
        return default_value
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_data():
    return load_json_file(DATA_FILE, [])


def save_data(data):
    save_json_file(DATA_FILE, data)


def load_memos():
    return load_json_file(MEMO_FILE, [])


def save_memos(data):
    save_json_file(MEMO_FILE, data)


def extract_owner(line):
    match = re.match(r"^\s*([^：:\n]+)[：:]", line)
    if match:
        return match.group(1).strip()
    return "待确认"


def extract_deadline(line):
    keywords = [
        "今天 22:00 前",
        "今天晚上",
        "今天中午前",
        "今天",
        "今晚",
        "明天 12:00 前",
        "明天中午前",
        "明天下午",
        "明天上午",
        "明天晚上",
        "明天",
        "周五前",
        "周五下午",
        "周五",
        "本周",
        "这周"
    ]
    for keyword in keywords:
        if keyword in line:
            return keyword
    return "待确认"


def detect_priority(line):
    high_words = ["尽快", "马上", "立即", "今晚", "今天", "提测", "风险", "阻塞", "依赖", "上线", "还差", "影响"]
    for word in high_words:
        if word in line:
            return "高"
    return "中"


def extract_task_name(content):
    patterns = [
        r"(出[^，。；\n]*)",
        r"(提交[^，。；\n]*)",
        r"(补[^，。；\n]*)",
        r"(完成[^，。；\n]*)",
        r"(同步[^，。；\n]*)",
        r"(整理[^，。；\n]*)",
        r"(确认[^，。；\n]*)",
        r"(开始[^，。；\n]*)",
        r"(推进[^，。；\n]*)",
        r"(发送[^，。；\n]*)",
        r"(给到[^，。；\n]*)",
        r"(输出[^，。；\n]*)"
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()

    short = content.strip()
    if len(short) > 28:
        short = short[:28] + "..."
    return short if short else "待确认任务"


def analyze_input_text(text):
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    tasks = []
    risks = []
    confirmed_points = []

    task_keywords = ["出", "提交", "补", "完成", "同步", "整理", "确认", "开始", "推进", "发送", "给到", "输出"]
    risk_keywords = ["风险", "阻塞", "依赖", "来不及", "延期", "还差", "未完成", "影响", "卡住", "无法"]

    for index, line in enumerate(lines):
        owner = extract_owner(line)
        content = re.sub(r"^\s*[^：:\n]+[：:]", "", line).strip()

        if any(keyword in content for keyword in task_keywords):
            tasks.append({
                "task_id": datetime.now().strftime("%Y%m%d%H%M%S%f") + str(index + 1),
                "task_name": extract_task_name(content),
                "owner": owner,
                "deadline": extract_deadline(content),
                "priority": detect_priority(content),
                "status": "待开始"
            })

        if any(keyword in content for keyword in risk_keywords):
            risks.append(content)

        if "定下来" in content or "确认" in content or "先定" in content:
            confirmed_points.append(content)

    if not tasks:
        tasks.append({
            "task_id": datetime.now().strftime("%Y%m%d%H%M%S%f") + "1",
            "task_name": "整理本次讨论形成的行动项",
            "owner": "待确认",
            "deadline": "待确认",
            "priority": "中",
            "status": "待开始"
        })

    if not risks:
        risks.append("暂未识别出明确风险，建议继续关注关键任务节点和依赖关系。")

    if confirmed_points:
        summary = f"本次讨论已形成 {len(confirmed_points)} 项阶段性结论，识别出 {len(tasks)} 条待办事项。"
    else:
        summary = f"本次讨论围绕任务推进展开，识别出 {len(tasks)} 条待办事项，并提炼了关键风险。"

    return {
        "summary": summary,
        "tasks": tasks,
        "risks": risks,
        "mode": "fallback"
    }


@app.route("/")
def home():
    return jsonify({"message": "Talk2Task backend is running"})


@app.route("/api/fetch-chat", methods=["GET"])
def fetch_chat():
    demo_chat = """产品经理 小林：大家看下，官网改版这周要把首页方案定下来。
设计师 小周：我今晚可以先出第一版视觉草图。
前端 小陈：如果首页结构今天确定，我明天下午可以开始搭页面。
运营 小杨：Banner 文案我明天中午前给到。
产品经理 小林：好，那我们今天先确定信息架构，周四前完成设计初稿。
前端 小陈：另外小程序提测接口还差一个登录状态校验。
后端 老王：这个接口我今天晚上补。
产品经理 小林：好，提测时间先定周五下午。
运营 小杨：那我周五前同步活动页素材。"""
    return jsonify({
        "chat_text": demo_chat,
        "source": "最近同步的项目群聊"
    })


@app.route("/api/analyze", methods=["POST"])
def analyze_text():
    body = request.get_json()
    text = body.get("text", "").strip()

    if not text:
        return jsonify({"error": "请先提取群聊内容"}), 400

    result = analyze_input_text(text)

    records = load_data()
    records.append({
        "id": len(records) + 1,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_text": text,
        "result": result
    })
    save_data(records)

    return jsonify({
        "record_id": len(records),
        "summary": result["summary"],
        "tasks": result["tasks"],
        "risks": result["risks"],
        "mode": result.get("mode", "fallback")
    })


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(load_data())


@app.route("/api/history/<int:record_id>", methods=["DELETE"])
def delete_history_item(record_id):
    records = load_data()
    new_records = [item for item in records if item["id"] != record_id]

    if len(new_records) == len(records):
        return jsonify({"error": "未找到对应记录"}), 404

    save_data(new_records)
    return jsonify({"message": "删除成功"})


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    save_data([])
    return jsonify({"message": "已清空全部历史记录"})


@app.route("/api/tasks/status", methods=["POST"])
def update_task_status():
    body = request.get_json()
    record_id = body.get("record_id")
    task_id = body.get("task_id")
    new_status = body.get("status")

    if not record_id or not task_id or not new_status:
        return jsonify({"error": "缺少必要参数"}), 400

    records = load_data()
    updated = False

    for record in records:
        if record["id"] == record_id:
            tasks = record.get("result", {}).get("tasks", [])
            for task in tasks:
                if task.get("task_id") == task_id:
                    task["status"] = new_status
                    updated = True
                    break

    if not updated:
        return jsonify({"error": "未找到对应任务"}), 404

    save_data(records)
    return jsonify({"message": "状态更新成功"})


@app.route("/api/memos", methods=["GET"])
def get_memos():
    memos = load_memos()
    return jsonify(memos)


@app.route("/api/memos", methods=["POST"])
def add_memo():
    body = request.get_json()
    summary = body.get("summary", "").strip()
    tasks = body.get("tasks", [])
    risks = body.get("risks", [])

    if not summary and not tasks and not risks:
        return jsonify({"error": "没有可添加到备忘录的内容"}), 400

    memos = load_memos()
    memos.append({
        "id": len(memos) + 1,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "tasks": tasks,
        "risks": risks
    })
    save_memos(memos)

    return jsonify({"message": "已添加到备忘录"})


@app.route("/api/memos", methods=["DELETE"])
def clear_memos():
    save_memos([])
    return jsonify({"message": "已清空备忘录"})


if __name__ == "__main__":
    app.run(debug=True)