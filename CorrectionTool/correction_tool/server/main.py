import json
import os
import shutil
from datetime import datetime, timezone

import pandas
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import ASCENDING, MongoClient

app = Flask(__name__)
CORS(app)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://host.docker.internal:27017")
PORT = int(os.environ.get("PORT", "5000"))

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["validation"]

users_collection = db["users"]
all_projects_coll = db["all_projects"]
all_errors_coll = db["error_types"]

UPLOAD_FOLDER = 'temp_uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route("/login", methods=["POST"])
def login():
    content = request.get_json()
    username = content.get("username")
    password = content.get("password")

    all_projects = [p["project_name"] for p in all_projects_coll.find()]

    user_doc = users_collection.find_one({"username": username})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404
    if user_doc["password"] == password:
        return jsonify({
            "message": "Login successful",
            "success": True,
            "projects": all_projects,
            "user_role": user_doc.get("role", "user"),
        }), 200

    return jsonify({"error": "Invalid username or password"}), 401


@app.route("/signup", methods=["POST"])
def signup():
    content = request.get_json()
    users_collection.insert_one({
        "username": content.get("username"),
        "password": content.get("password"),
        "projects": content.get("projects", []),
    })
    return jsonify({"success": True}), 200


@app.route('/get_user_projects', methods=['POST'])
def get_projects():
    to_return = {proj["project_name"] for proj in all_projects_coll.find()}
    return jsonify({"projects": list(to_return)}), 200


@app.route("/get_all_projects", methods=["GET"])
def get_all_projects():
    to_return = {proj["project_name"] for proj in all_projects_coll.find()}
    return jsonify({"projects": list(to_return)}), 200


@app.route("/add_user_project", methods=["POST"])
def add_project():
    content = request.get_json()
    username = content.get("username")
    project_name = content.get("project_name")

    if not username or not project_name:
        return jsonify({"error": "Username and project name are required"}), 400

    all_projects_coll.insert_one({"project_name": project_name, "created_by": username, "log": []})
    return jsonify({"message": "Project added successfully"}), 200


@app.route("/get_correction_data", methods=["POST"])
def get_correction_data():
    content = request.get_json()
    project_name = content["project_name"]
    username = content.get("username", "unknown_user")
    collection_name = f"{project_name}_data"

    if collection_name not in db.list_collection_names():
        new_coll = db.create_collection(collection_name)
        new_coll.create_index([("id", ASCENDING)], unique=True)

    data_collection = db[collection_name]

    pipeline = [
        {"$match": {"corrected_json": {"$exists": False}}},
        {"$sample": {"size": 1}},
    ]

    random_docs = list(data_collection.aggregate(pipeline))
    if not random_docs:
        return jsonify({"correction_data": None, "message": "No uncorrected documents found"}), 200

    random_doc = random_docs[0]
    random_doc.pop("_id", None)

    random_doc["total_num"] = data_collection.count_documents({})
    random_doc["total_corrected"] = data_collection.count_documents({"corrected_json": {"$exists": True}})
    random_doc["total_corrected_by_user"] = data_collection.count_documents({"corrected_by": username})

    error_types = []
    for error_type in all_errors_coll.find():
        error_type.pop("_id", None)
        error_types.append(error_type)
    random_doc["error_types"] = error_types

    return jsonify({"correction_data": random_doc}), 200


@app.route("/upload_data", methods=["POST"])
def upload_data():
    project_name = request.form.get("project_name")
    matching_key_src = request.form.get("matching_key_src")
    matching_key_target = request.form.get("matching_key_target")
    source_file = request.files.get("source_data")
    extracted_file = request.files.get("extracted_data")

    if not project_name or not matching_key_src or not matching_key_target or not source_file or not extracted_file:
        return jsonify({"error": "project_name, matching_key, source_data and extracted_data are required"}), 400

    collection_obj = db[f"{project_name}_data"]

    try:
        source_list = pandas.read_csv(source_file).to_dict(orient='records')
        extracted_list = json.load(extracted_file)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON upload: {str(e)}"}), 400

    if not isinstance(source_list, list) or not isinstance(extracted_list, list):
        return jsonify({"error": "Uploaded JSON must be an array of objects"}), 400

    extracted_index = {item[matching_key_target]: item for item in extracted_list if matching_key_target in item}

    try:
        max_id = collection_obj.find_one(sort=[("id", -1)])["id"]
    except TypeError:
        max_id = 0
    next_id = max_id + 1

    added = 0
    to_add = []
    for src in source_list:
        ext = extracted_index.get(src.get(matching_key_src))
        if ext is not None:
            to_add.append({"id": next_id, "text": src["text"], "extracted_json": ext})
            next_id += 1
            added += 1

    collection_obj.insert_many(to_add)
    return jsonify({"message": f"Added {added} documents to project '{project_name}'", "project_size": added}), 200


@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    upload_id = request.form.get("upload_id")
    chunk_index = request.form.get("chunk_index")
    chunk_file = request.files.get("chunk")

    if not all([upload_id, chunk_index, chunk_file]):
        return jsonify({"error": "Missing chunk data"}), 400

    temp_dir = os.path.join(UPLOAD_FOLDER, upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    chunk_file.save(os.path.join(temp_dir, f"chunk_{chunk_index}.part"))

    return jsonify({"message": f"Chunk {chunk_index} for {upload_id} received"}), 200


def reassemble_file(upload_id, final_path):
    temp_dir = os.path.join(UPLOAD_FOLDER, upload_id)
    if not os.path.isdir(temp_dir):
        raise FileNotFoundError(f"Upload directory not found for {upload_id}")

    chunk_files = [f for f in os.listdir(temp_dir) if f.startswith('chunk_')]
    chunk_files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

    with open(final_path, 'wb') as final_file:
        for chunk_filename in chunk_files:
            with open(os.path.join(temp_dir, chunk_filename), 'rb') as chunk_file:
                final_file.write(chunk_file.read())


@app.route("/process_uploaded_data", methods=["POST"])
def process_uploaded_data():
    project_name = request.form.get("project_name")
    matching_key_src = request.form.get("matching_key_src")
    matching_key_target = request.form.get("matching_key_target")
    source_upload_id = request.form.get("source_upload_id")
    source_filename = request.form.get("source_filename")
    extracted_upload_id = request.form.get("extracted_upload_id")
    extracted_filename = request.form.get("extracted_filename")

    if not all([project_name, matching_key_src, matching_key_target, source_upload_id, extracted_upload_id]):
        return jsonify({"error": "Missing finalization data"}), 400

    source_path = os.path.join(UPLOAD_FOLDER, source_filename)
    extracted_path = os.path.join(UPLOAD_FOLDER, extracted_filename)

    try:
        reassemble_file(source_upload_id, source_path)
        reassemble_file(extracted_upload_id, extracted_path)
        collection_obj = db[f"{project_name}_data"]

        source_list = pandas.read_csv(source_path).to_dict(orient='records')
        with open(extracted_path, 'r', encoding='utf-8') as f:
            extracted_list = json.load(f)

        if not isinstance(source_list, list) or not isinstance(extracted_list, list):
            return jsonify({"error": "Uploaded data must be an array of objects"}), 400

        extracted_index = {item.get(matching_key_target): item for item in extracted_list if matching_key_target in item}

        try:
            max_id = collection_obj.find_one(sort=[("id", -1)])["id"]
        except (TypeError, IndexError):
            max_id = 0
        next_id = max_id + 1

        to_add = []
        for src in source_list:
            ext = extracted_index.get(src.get(matching_key_src))
            if ext is not None:
                detected_errors_list = ext.pop('detected_errors', [])
                to_add.append({
                    "id": next_id,
                    "text": src["text"],
                    "extracted_json": ext,
                    "detected_errors": detected_errors_list,
                })
                next_id += 1

        if to_add:
            collection_obj.insert_many(to_add)

        return jsonify({
            "message": f"Added {len(to_add)} documents to project '{project_name}'",
            "project_size": len(to_add),
        }), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred during processing: {str(e)}"}), 500
    finally:
        if os.path.exists(source_path):
            os.remove(source_path)
        if os.path.exists(extracted_path):
            os.remove(extracted_path)
        shutil.rmtree(os.path.join(UPLOAD_FOLDER, source_upload_id), ignore_errors=True)
        shutil.rmtree(os.path.join(UPLOAD_FOLDER, extracted_upload_id), ignore_errors=True)


@app.route("/get_error_types", methods=["GET"])
def get_error_types():
    all_errors = list(all_errors_coll.find())
    if not all_errors:
        return jsonify({"message": "No error types found"}), 404
    return jsonify({"errors": all_errors}), 200


@app.route("/new_error_type", methods=["POST"])
def new_error_type():
    content = request.get_json()
    all_errors_coll.insert_one({"name": content["name"], "description": content["description"]})
    return jsonify({"success": True}), 200


@app.route("/add_corrected_document", methods=["POST"])
def add_corrected_document():
    content = request.get_json()
    data_collection = db[f"{content['project_name']}_data"]
    data_collection.update_one({"id": content["id"]}, {
        "$set": {
            "corrected_json": content["corrected_json"],
            "correction_log": content["correction_log"],
            "dismissed_flags": content.get("dismissed_flags", []),
            "corrected_by": content["username"],
            "corrected_at": datetime.now(timezone.utc),
            "corrected": True,
        }
    })
    return jsonify({"message": "Document corrected successfully", "success": True}), 200


@app.route("/get_analytics", methods=["GET"])
def get_analytics():
    projects = [p["project_name"] for p in all_projects_coll.find()]
    users = [u["username"] for u in users_collection.find()]

    analytics_data = {}
    for project in projects:
        collection_name = f"{project}_data"
        if collection_name not in db.list_collection_names():
            analytics_data[project] = {
                "total_docs": 0,
                "total_corrected": 0,
                "completion_percentage": 0,
                "total_corrected_by_user": {user: 0 for user in users},
            }
            continue

        data_collection = db[collection_name]
        pipeline = [{
            "$facet": {
                "total_docs": [{"$count": "count"}],
                "total_corrected": [
                    {"$match": {"corrected_json": {"$exists": True}}},
                    {"$count": "count"},
                ],
                "corrected_by_user": [
                    {"$match": {"corrected_by": {"$exists": True}}},
                    {"$group": {"_id": "$corrected_by", "count": {"$sum": 1}}},
                ],
            }
        }]

        result = list(data_collection.aggregate(pipeline))
        if not result:
            analytics_data[project] = {
                "total_docs": 0,
                "total_corrected": 0,
                "completion_percentage": 0,
                "total_corrected_by_user": {user: 0 for user in users},
            }
            continue

        data = result[0]
        total_docs = data["total_docs"][0]["count"] if data["total_docs"] else 0
        total_corrected = data["total_corrected"][0]["count"] if data["total_corrected"] else 0
        user_counts = {item["_id"]: item["count"] for item in data["corrected_by_user"]}

        analytics_data[project] = {
            "total_docs": total_docs,
            "total_corrected": total_corrected,
            "completion_percentage": (total_corrected / total_docs * 100) if total_docs > 0 else 0,
            "total_corrected_by_user": {user: user_counts.get(user, 0) for user in users},
        }

    return jsonify({"analytics": analytics_data}), 200


@app.route("/admin/get_users", methods=["GET"])
def get_all_users():
    user_list = list(users_collection.find({"role": {"$ne": "admin"}}, {"username": 1, "_id": 0}))
    return jsonify({"users": [user['username'] for user in user_list]}), 200


@app.route("/admin/get_user_projects", methods=["GET"])
def get_user_projects_for_admin():
    username = request.args.get("username")
    if not username:
        return jsonify({"error": "Username is required"}), 400

    worked_on_projects = []
    for project_name in [p["project_name"] for p in all_projects_coll.find()]:
        collection_name = f"{project_name}_data"
        if collection_name in db.list_collection_names():
            if db[collection_name].count_documents({"corrected_by": username}) > 0:
                worked_on_projects.append(project_name)

    return jsonify({"projects": worked_on_projects}), 200


@app.route("/admin/get_corrected_documents", methods=["GET"])
def get_corrected_documents():
    username = request.args.get("username")
    project_name = request.args.get("project_name")

    if not username or not project_name:
        return jsonify({"error": "Username and project name are required"}), 400

    documents = list(db[f"{project_name}_data"].find(
        {"corrected_by": username, "approved": {"$ne": True}},
        {"_id": 0},
    ).sort("corrected_at", -1))

    return jsonify({"documents": documents}), 200


@app.route("/admin/review_correction", methods=["POST"])
def review_correction():
    content = request.get_json()
    project_name = content.get("project_name")
    document_id = content.get("document_id")
    action = content.get("action")
    admin_username = content.get("admin_username")

    if not all([project_name, document_id, action, admin_username]):
        return jsonify({"error": "Missing required fields (project_name, document_id, action, admin_username)"}), 400

    data_collection = db[f"{project_name}_data"]

    if action == "approve":
        corrected_json = content.get("corrected_json")
        if corrected_json is None:
            return jsonify({"error": "corrected_json is required for approval"}), 400

        update_result = data_collection.update_one(
            {"id": document_id},
            {"$set": {
                "corrected_json": corrected_json,
                "approved": True,
                "approved_by": admin_username,
                "approved_at": datetime.now(timezone.utc),
            }},
        )
        if update_result.matched_count == 0:
            return jsonify({"error": "Document not found"}), 404
        return jsonify({"message": "Document approved successfully"}), 200

    if action == "reject":
        update_result = data_collection.update_one(
            {"id": document_id},
            {"$unset": {
                "corrected_json": "", "correction_log": "", "dismissed_flags": "", "corrected_by": "", "corrected_at": "",
                "corrected": "", "approved": "", "approved_by": "", "approved_at": "",
            }},
        )
        if update_result.matched_count == 0:
            return jsonify({"error": "Document not found"}), 404
        return jsonify({"message": "Document rejected and reverted to its original state"}), 200

    return jsonify({"error": "Invalid action specified. Must be 'approve' or 'reject'."}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
