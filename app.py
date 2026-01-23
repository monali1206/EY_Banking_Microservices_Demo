import uuid, os
from datetime import datetime
from flask import Flask
from flask.views import MethodView
from flask_smorest import Api, Blueprint, abort
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, validate

app = Flask(__name__)

# --- CONFIGURATION ---
app.config.update({
    "API_TITLE": "KYC Onboarding Service",
    "API_VERSION": "v1",
    "OPENAPI_VERSION": "3.0.3",
    "OPENAPI_URL_PREFIX": "/",
    "OPENAPI_SWAGGER_UI_PATH": "/swagger-ui",
    "OPENAPI_SWAGGER_UI_URL": "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    # Persistent Database Connection
    "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL", "postgresql://admin:securepassword@db:5432/bank_onboarding_db"),
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", "bank-fixed-secret-key"),
    "API_SPEC_OPTIONS": {
        "security": [{"bearerAuth": []}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}}
    }
})

# Initialize Database and Security
db = SQLAlchemy(app)
api = Api(app)
jwt = JWTManager(app)
blp = Blueprint("kyc", "kyc", description="KYC Operations")

# --- DATABASE MODELS ---

class SessionModel(db.Model):
    __tablename__ = 'kyc_sessions'
    id = db.Column(db.String(50), primary_key=True)
    kyc_purpose = db.Column(db.String(100))
    jurisdiction = db.Column(db.String(10))
    status = db.Column(db.String(20), default="CREATED")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationship to track documents for the summary
    documents = db.relationship("DocumentModel", backref="session", lazy=True)

class DocumentModel(db.Model):
    __tablename__ = 'kyc_documents'
    id = db.Column(db.String(50), primary_key=True)
    session_id = db.Column(db.String(50), db.ForeignKey('kyc_sessions.id'), nullable=False)
    document_type = db.Column(db.String(50))
    side = db.Column(db.String(10))
    country = db.Column(db.String(50))
    state = db.Column(db.String(20), default="UPLOADED")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- SCHEMAS ---

class SessionSchema(Schema):
    kycPurpose = fields.Str(required=True)
    jurisdiction = fields.Str(required=True, validate=validate.OneOf(['IN']))
    customer = fields.Dict(required=True)

class KycDocSchema(Schema):
    documentType = fields.Str(required=True, validate=validate.OneOf(['PAN', 'AADHAAR', 'PASSPORT', 'VOTER_ID']))
    side = fields.Str(required=True, validate=validate.OneOf(['FRONT', 'BACK']))
    country = fields.Str(required=True)

# --- ROUTES ---

@blp.route("/login")
class Login(MethodView):
    def post(self):
        return {"access_token": create_access_token(identity="admin")}

@blp.route("/v1/kyc/sessions")
class Sessions(MethodView):
    @jwt_required()
    @blp.arguments(SessionSchema)
    def post(self, data):
        session_id = f"sess_{uuid.uuid4().hex[:8].upper()}"
        new_session = SessionModel(
            id=session_id,
            kyc_purpose=data['kycPurpose'],
            jurisdiction=data['jurisdiction']
        )
        db.session.add(new_session)
        db.session.commit()
        return {"sessionId": new_session.id, "status": new_session.status}, 201

@blp.route("/v1/kyc/sessions/<string:sessionId>/documents")
class Docs(MethodView):
    @jwt_required()
    @blp.arguments(KycDocSchema, location="form")
    def post(self, data, sessionId):
        # Verify session exists first
        session = SessionModel.query.get_or_404(sessionId)
        
        doc_id = f"doc_{uuid.uuid4().hex[:8].upper()}"
        new_doc = DocumentModel(
            id=doc_id,
            session_id=sessionId,
            document_type=data['documentType'],
            side=data['side'],
            country=data['country']
        )
        db.session.add(new_doc)
        db.session.commit()
        return {"documentId": new_doc.id, "status": new_doc.state}, 201

@blp.route("/v1/kyc/sessions/<string:sessionId>/summary")
class Summary(MethodView):
    @jwt_required()
    def get(self, sessionId):
        session = SessionModel.query.get_or_404(sessionId)
        docs = [{"id": d.id, "type": d.document_type, "status": d.state} for d in session.documents]
        
        return {
            "sessionId": sessionId,
            "status": session.status,
            "documentCount": len(docs),
            "documents": docs
        }, 200

api.register_blueprint(blp)

if __name__ == "__main__":
    # Create tables before starting the app
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5001)