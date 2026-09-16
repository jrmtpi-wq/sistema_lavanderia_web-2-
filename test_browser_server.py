"""Servidor de teste isolado. Não usa o banco local ou o do Render."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
from datetime import timedelta
from app import app, db, init_db, Carga, Maquina
from operacao import agora_local

if __name__ == '__main__':
    with app.app_context():
        init_db()
        machine=Maquina.query.filter_by(tipo='lavar').first()
        db.session.add(Carga(maquina_id=machine.id,numero=1,op_manual='DEMO-001',
                             referencia='Jeans de teste',peso=80,qtde_pecas=100,
                             data_inicio=agora_local()-timedelta(hours=2)))
        db.session.commit()
    app.run(host='127.0.0.1',port=5001,debug=False,threaded=False)
