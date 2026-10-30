"""Documentation scenes using the production Maintenance UI with example records.

Fixtures follow real controller/evidence contracts; no physical result is claimed.
The renderer is invoked only in CI, never on the development machine.
"""
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from petrel.features.maintenance.assessment.store import ServicePolicy
from petrel.features.maintenance.assessment.model import Finding
from petrel.features.maintenance.domains.sensors.diagnostics import SensorReading

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
                  ('cpu.cpu6',35.),('cpu.cpu7',41.),('cpu.cpu8',34.),('cpu.cpu9',31.),
                  ('cpu.cpu10',32.),('cpu.cpu11',37.),('cpu.cpu12',39.),
                  ('cpu.cpu13',30.),('cpu.cpu14',36.),('cpu.cpu15',33.),
                  ('memory.total',949000),('memory.available',193992),('memory.used',755008)))
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


    # Every example below renders the production Maintenance screen model.
    # Hardware values are documented fixtures, never physical measurements.
    def care_device(v):
        v.pd.maintenance_service_devices=Mock(return_value=(
            'stepper_x','stepper_y','stepper_z','extruder','heater_bed',
            'fan','endstop stepper_x','filament_switch_sensor gate'))
    add('maintenance-care-device','Choose a discovered component for a new reminder',
        'Yeni hatırlatıcı için keşfedilen donanımı seçme','service_devices',1,care_device)

    add('maintenance-care-class','Choose a hotend maintenance task',
        'Hotend bakım görevini seçme','service_kind',1,
        lambda v:setattr(v,'_maintenance_context','extruder'))

    def filament_basis(v):
        v._maintenance_context=('extruder','nozzle')
        v.pd.maintenance_service_bases=Mock(return_value=(
            'calendar_s','sampled_print_s','filament_mm','sampled_on_s'))
    add('maintenance-care-basis','Select calendar, print, ON or extruded filament usage',
        'Takvim, baskı, ON veya filament uzunluğu sayacı seçimi',
        'service_basis',3,filament_basis)

    def interval(v):
        v._maintenance_context=('extruder','nozzle',500,'filament_mm')
    add('maintenance-care-interval','Edit the nozzle inspection interval in metres',
        'Nozzle kontrol aralığını metre olarak düzenleme','service_interval',1,interval)

    nozzle=ServicePolicy('nozzle','extruder','filament_mm',500000,'user')
    def review(v):
        v._maintenance_context=nozzle
    add('maintenance-care-review','Review a filament-based reminder before saving',
        'Filament bazlı hatırlatıcıyı kaydetmeden önce gözden geçirme',
        'service_review',1,review)

    def detail(v):
        v._maintenance_context=(nozzle,{'_sampled_elapsed_s':120000},'unknown')
    add('maintenance-care-detail','View recorded progress for a nozzle reminder',
        'Nozzle hatırlatıcısının kayıtlı ilerleme ayrıntısı',
        'service_task',1,detail)

    add('maintenance-care-complete','Confirm a completed physical maintenance task',
        'Gerçekten yapılan bakımın kaydını onaylama','service_confirm',1,review)
    add('maintenance-care-remove','Confirm reminder removal while preserving history',
        'Geçmişi koruyarak hatırlatıcı silmeyi onaylama',
        'service_remove_confirm',0,review)

    add('maintenance-usage-menu','Usage and history entry points',
        'Kullanım ve geçmiş menüsü','history',1)
    component_usage=NS(feature_id='S12',device=None,status=None,reason='observed_information',
        evidence=(('sampled_print_s',68400),
                  ('stepper_x.travel_mm',32480),('stepper_y.travel_mm',28750),
                  ('stepper_z.travel_mm',430),
                  ('fan.sampled_on_s',14020),('extruder.sampled_on_s',19980),
                  ('endstop stepper_x.trigger_count',105),
                  ('filament_switch_sensor gate.trigger_count',57)))
    add('maintenance-usage-component','Recorded axis travel, powered hours and sensor events',
        'Kayıtlı eksen mesafesi, açık kalma süresi ve sensör olayları',
        'result',0,lambda v:setattr(v,'_maintenance_result',component_usage))

    def sensor_list(v):
        v.pd.maintenance_sensor_devices=Mock(return_value=(
            'endstop stepper_x','endstop stepper_y','probe',
            'filament_switch_sensor gate'))
    add('maintenance-sensor-list','Discovered sensor diagnostics list',
        'Keşfedilen sensörlerin diagnostik listesi','sensor_devices',1,sensor_list)

    sensor=SensorReading('filament_switch_sensor gate',
        'filament_switch_sensor gate',True,True,
        (('Sensor enabled','Yes'),('Filament detected','Yes')),
        ('Snapshot at read time; use Refresh for another reading.',))
    add('maintenance-sensor-report','On-demand filament sensor status report',
        'İstek üzerine filament sensörü durum raporu',
        'sensor_report',0,lambda v:setattr(v,'_maintenance_context',sensor))
