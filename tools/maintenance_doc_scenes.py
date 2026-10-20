"""Documentation scenes using the production Maintenance UI with example records.

Fixtures follow real controller/evidence contracts; no physical result is claimed.
The renderer is invoked only in CI, never on the development machine.
"""
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from maintenance_assessment_store import ServicePolicy
from maintenance_assessment_model import Finding

NOW=1780000000

def register(scene,canvas,finish):
    def view(page='root',selection=0):
        v=canvas()
        v._maintenance_init();v.checkkey=v.MaintenanceMenu
        v._maintenance_page=page;v._maintenance_selection=selection
        physical=tuple(NS(feature_id=f,device=d,method=m,visible=True) for f,d,m in (
            ('F02','fan',2),('F12','fan',2),('H01','extruder',2),('H01','heater_bed',2),
            ('M01','stepper_x',2),('M12','stepper_x',8),('P03','probe',2),('S18','buzzer',2),('O04','neopixel mmu_leds',2)))
        reads=tuple(NS(feature_id=f,device=None,method=1,visible=True) for f in ('S01','S02','S03','S10'))
        v.pd.maintenance_guided_plan=Mock(return_value=physical)
        v.pd.maintenance_read_plan=Mock(return_value=reads)
        v.pd.maintenance_pulse=NS(phase=None,pending=False,available=lambda:())
        v.pd.maintenance_assessment.has_current_evidence=Mock(return_value=True)
        findings=(Finding('check.H07','extruder','attention','thermal.overshoot_review'),)
        v.pd.maintenance_assessment_details=Mock(return_value=NS(findings=findings,trends=()))
        v._maintenance_records_ready=True;v._maintenance_records_identity=v._maintenance_identity()
        plans=(('lubricate','stepper_x',30,26),('lubricate','stepper_y',30,12),
               ('nozzle_inspect','extruder',60,44),('inspect_clean','fan',30,8),
               ('inspect_clean','heater_bed',30,3))
        v._maintenance_records_data=(tuple((ServicePolicy(task,device,'calendar_s',days*86400,'user'),
             {'timestamp':NOW-age*86400},'not_due') for task,device,days,age in plans),())
        # The demo includes a fifth supported target for the five-plan care example.
        extra=NS(feature_id='M01',device='stepper_y',method=2,visible=True)
        v.pd.maintenance_guided_plan.return_value=physical+(extra,)
        return v

    def draw(page='root',selection=0,configure=None):
        v=view(page,selection)
        if configure: configure(v)
        with patch.dict(v._maintenance_care.__func__.__globals__,time=lambda:NOW):
            v.Draw_Maintenance_Menu()
        return finish(v)

    def add(name,en,tr,page='root',selection=0,configure=None):
        scene(name,'maintenance',en,tr)(lambda:draw(page,selection,configure))

    add('maintenance','Care overview and fixed Maintenance destinations','Bakım özeti ve sabit Maintenance bölümleri')
    add('maintenance-care','Five saved care plans, first page','Beş kayıtlı bakım planı, ilk görünüm','service',1)
    add('maintenance-care-scrolled','Remaining care plans after scrolling','Kaydırma sonrası diğer bakım planları','service',5)
    add('maintenance-checks','Checks grouped by installed capability','Kurulu donanıma göre gruplandırılan testler','groups',1)
    add('maintenance-prepare','Fan check preparation before any command','Komut çalıştırılmadan önce fan testi hazırlığı','prepare',1,
        lambda v:setattr(v,'_maintenance_context',v.pd.maintenance_guided_plan()[0]))
    add('maintenance-diagnostics','Diagnostics, usage and support entry points','Diagnostik, kullanım ve destek girişleri','diagnostic_groups',1)

    host=NS(feature_id='S01',device=None,status=None,reason='observed_information',
        evidence=(('cpu.cpu',36.5),('cpu.cpu0',42.1),('cpu.cpu1',30.9),('cpu.cpu2',35.2),
                  ('cpu.cpu3',37.8),('cpu.cpu4',30.),('cpu.cpu5',40.),
                  ('cpu.cpu6',35.),('cpu.cpu7',41.),('memory.total',949000),('memory.available',193992),('memory.used',755008)))
    def host_scroll(v,offset=0):
        v._maintenance_result=host;v._maintenance_report_position=offset
    add('maintenance-host','Host readings as labeled measurements','Etiketli ölçümler olarak host verileri','result',0,host_scroll)
    add('maintenance-host-page-2','Host information after scrolling','Kaydırma sonrası host bilgileri','result',0,lambda v:host_scroll(v,3))

    fan=NS(feature_id='F02',device='fan',status='PASSED_USER',reason='',evidence=(),restore_verified=True)
    add('maintenance-result','Recorded fan observation with separate actions','Ayrı işlem alanıyla kaydedilen fan gözlemi','result',1,
        lambda v:setattr(v,'_maintenance_result',fan))
    thermal=NS(feature_id='H07',device='extruder',status='FAILED_METRIC',reason='thermal_metric_threshold_exceeded',
        evidence=(('overshoot_c',7.72),('target',60),('temperature',67.72)),restore_verified=True)
    combined=NS(feature_id='H01',device='extruder',status='PASSED_USER',reason='',evidence=(),
        components=(thermal,),restore_verified=True)
    add('maintenance-thermal-result','Heating result explains a measurement requiring review','İncelenmesi gereken ölçümü açıklayan ısıtma sonucu','result',0,
        lambda v:setattr(v,'_maintenance_result',combined))
    add('maintenance-evidence','Optional heating measurements without menu cursors','Menü seçim çizgileri olmadan isteğe bağlı ısıtma ölçümleri','details',0,
        lambda v:setattr(v,'_maintenance_context',thermal))
    add('maintenance-recommendation','Recommendation explanation and available follow-up','Önerinin açıklaması ve kullanılabilir sonraki işlemler','finding',0,
        lambda v:setattr(v,'_maintenance_context',v.pd.maintenance_assessment_details().findings))
