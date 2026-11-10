"""Real Chromium + production React + real Express/MongoDB; no route mocks."""
import json,os,time,unittest,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from playwright.sync_api import sync_playwright,expect

ROOT=Path('/demo-private');FIXTURE=json.loads((ROOT/'credentials.json').read_text());URL=os.environ['PORTAL_TEST_URL']
class PortalBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.play=sync_playwright().start();cls.browser=cls.play.chromium.launch(headless=True);print('Browser runtime: Chromium '+cls.browser.version,flush=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.play.stop()
    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1440,'height':1050},locale='en-US')
        self.page=self.context.new_page();self.token=None
        def response(r):
            if r.url.endswith('/auth/login') and r.status==200:self.token=r.json()['token']
        self.page.on('response',response)
        self.page.goto(URL)
    def tearDown(self):self.context.close()
    def login(self,role='patient',page=None):
        page=page or self.page;account=FIXTURE['users'][role]
        page.get_by_label('Email address').fill(account['email']);page.get_by_label('Password',exact=True).fill(account['password']);page.get_by_role('button',name='Sign in',exact=True).click()
        expect(page.get_by_role('button',name='Sign out',exact=True)).to_be_visible()
        if role in {'patient','otherPatient','doctor'}:expect(page.get_by_role('button',name='Refresh records')).to_be_enabled()
    def control(self,action):
        command={'id':str(uuid.uuid4()),'action':action};temp=ROOT/'control-next.json';temp.write_text(json.dumps(command));temp.replace(ROOT/'control.json')
        for _ in range(100):
            try:
                if json.loads((ROOT/'control-ack.json').read_text())['id']==command['id']:return
            except FileNotFoundError:pass
            time.sleep(.1)
        self.fail('Private fixture control did not acknowledge')
    def api(self,method,path,token=None,body=None):
        return self.page.request.fetch(URL+path,method=method,headers={'Authorization':'Bearer '+(token or self.token)},data=body)
    def book(self):
        self.page.get_by_role('button',name='Book appointment').first.click();expect(self.page.get_by_text('Appointment booked.',exact=True)).to_be_visible()
        expect(self.page.locator('.appointment').filter(has=self.page.get_by_text('confirmed',exact=True))).to_have_count(1)
    def cancel(self,page=None):
        page=page or self.page
        row=page.locator('.appointment').filter(has=page.get_by_text('confirmed',exact=True)).first
        row.get_by_role('button',name='Cancel appointment',exact=True).click();row.get_by_role('button',name='Confirm cancellation',exact=True).click();expect(page.get_by_text('Appointment cancelled.',exact=True)).to_be_visible()
    def test_01_registration_and_reload_have_no_persistent_credentials(self):
        self.page.get_by_role('link',name='Register as a patient').click()
        self.page.get_by_label('Full name').fill('Synthetic new patient');self.page.get_by_label('Email address').fill('new-'+uuid.uuid4().hex+'@example.test');self.page.get_by_label('Password',exact=True).fill('Synthetic-'+uuid.uuid4().hex)
        self.page.get_by_role('button',name='Create patient account').click();expect(self.page.get_by_role('heading',name='My appointments')).to_be_visible()
        self.assertEqual(self.page.evaluate('localStorage.length + sessionStorage.length'),0);self.assertEqual(self.context.cookies(),[])
        self.page.reload();expect(self.page.get_by_role('button',name='Sign in',exact=True)).to_be_visible()
    def test_02_booking_cross_patient_isolation_and_cancellation(self):
        self.login();self.book()
        response=self.api('GET','/api/appointments');self.assertEqual(response.headers['cache-control'],'no-store');records=response.json()['appointments'];record=next(r for r in records if r['status']=='confirmed')
        other=self.context.new_page();other_token=[]
        other.on('response',lambda r:other_token.append(r.json()['token']) if r.url.endswith('/auth/login') and r.status==200 else None)
        other.goto(URL);self.login('otherPatient',other)
        expect(other.get_by_text('No appointments here yet')).to_be_visible()
        self.assertEqual(self.api('GET','/api/appointments/'+record['_id'],other_token[-1]).status,404)
        self.assertEqual(self.api('POST','/api/availability',body={'date':FIXTURE['date'],'startTime':'12:00','endTime':'13:00'}).status,403)
        self.page.screenshot(path=str(ROOT/'patient-desktop.png'),full_page=True)
        self.cancel();self.assertEqual(self.api('GET','/api/appointments/'+record['_id']).json()['appointment']['status'],'cancelled')
    def test_03_doctor_publishes_edits_and_removes_availability(self):
        self.login('doctor');date=(datetime.now(timezone.utc)+timedelta(days=4)).date().isoformat()
        form=self.page.locator('.schedule-form');form.get_by_label('Date (UTC)').fill(date);form.get_by_label('Start time (UTC)').fill('14:00');form.get_by_label('End time (UTC)').fill('14:30');form.get_by_role('button',name='Publish availability').click();expect(self.page.get_by_text('Availability published.',exact=True)).to_be_visible()
        slot=self.page.locator('.slot').filter(has_text='14:00 – 14:30 UTC');slot.get_by_role('button',name='Edit slot').click();form=self.page.locator('.schedule-form');form.get_by_label('Start time (UTC)').fill('14:15');form.get_by_role('button',name='Save slot').click();expect(self.page.get_by_text('Availability updated.',exact=True)).to_be_visible()
        self.page.screenshot(path=str(ROOT/'doctor-desktop.png'),full_page=True)
        self.page.locator('.slot').filter(has_text='14:15 – 14:30 UTC').get_by_role('button',name='Remove slot').click();expect(self.page.get_by_text('Availability removed.',exact=True)).to_be_visible();expect(self.page.locator('.slot').filter(has_text='14:15 – 14:30 UTC')).to_have_count(0)
    def test_04_doctor_sees_assigned_booking_and_booked_controls_are_disabled(self):
        self.login();self.book();doctor=self.context.new_page();doctor.goto(URL);self.login('doctor',doctor)
        expect(doctor.locator('.appointment').filter(has=doctor.get_by_text('confirmed',exact=True))).to_have_count(1)
        booked=doctor.locator('.slot').filter(has=doctor.get_by_text('Booked',exact=True));expect(booked.get_by_role('button',name='Edit slot')).to_be_disabled();expect(booked.get_by_role('button',name='Remove slot')).to_be_disabled()
        self.cancel(doctor)
    def test_05_logout_revokes_actual_server_session(self):
        self.login();token=self.token;self.page.get_by_role('button',name='Sign out',exact=True).click();expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible();self.assertEqual(self.api('GET','/api/appointments',token).status,401);expect(self.page.get_by_role('button',name='Sign in',exact=True)).to_be_visible()
    def test_06_actual_stored_expiry_removes_private_dashboard(self):
        self.login();self.control('expire');self.page.get_by_role('button',name='Refresh records').click();expect(self.page.get_by_text('Your session ended. Sign in again.',exact=True)).to_be_visible();expect(self.page.get_by_role('heading',name='My appointments')).to_have_count(0)
    def test_07_forbidden_route_and_staff_navigation(self):
        self.login();self.page.evaluate("history.pushState(null,'','/doctor');dispatchEvent(new PopStateEvent('popstate'))")
        expect(self.page.get_by_text('This workspace is not available to your account.',exact=True)).to_be_visible()
        self.page.get_by_role('button',name='Sign out',exact=True).click();expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible()
        for role,heading in [('technician','Assessment workspace'),('admin','Identity administration')]:
            self.login(role);expect(self.page.get_by_role('heading',name=heading,exact=True)).to_be_visible();self.assertEqual(self.api('GET','/api/appointments').status,403)
            self.page.get_by_role('link',name='Account & security',exact=True).click();expect(self.page.get_by_role('heading',name='Session & access')).to_be_visible();expect(self.page.get_by_text('Loading…',exact=True)).to_have_count(0)
            self.page.get_by_role('button',name='Sign out',exact=True).click();expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible()
    def test_08_real_api_outage_recovers_without_fake_data(self):
        self.login();self.control('pause')
        try:
            self.page.get_by_role('button',name='Refresh records').click();expect(self.page.get_by_role('alert')).to_contain_text('unavailable');expect(self.page.locator('.appointment')).to_have_count(0)
        finally:self.control('resume')
        self.page.get_by_role('button',name='Refresh records').click();expect(self.page.get_by_role('heading',name='My appointments')).to_be_visible();expect(self.page.get_by_role('alert')).to_have_count(0)
    def test_09_conflicts_validation_and_mobile_layout(self):
        self.page.get_by_label('Email address').fill('missing@example.test');self.page.get_by_label('Password',exact=True).fill('Synthetic-invalid-password');self.page.get_by_role('button',name='Sign in',exact=True).click();expect(self.page.get_by_role('alert')).to_contain_text('Email or password not accepted')
        self.login('doctor');form=self.page.locator('.schedule-form');form.get_by_label('Date (UTC)').fill(FIXTURE['date']);form.get_by_label('Start time (UTC)').fill('09:00');form.get_by_label('End time (UTC)').fill('09:30');form.get_by_role('button',name='Publish availability').click();expect(self.page.get_by_role('alert')).to_contain_text('Refresh before trying again')
        self.page.set_viewport_size({'width':390,'height':844});self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),390);expect(self.page.get_by_role('button',name='Sign out',exact=True)).to_be_visible();self.page.screenshot(path=str(ROOT/'doctor-mobile.png'),full_page=True)
        self.page.get_by_role('button',name='Sign out',exact=True).click();expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible();self.login();self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),390);self.page.screenshot(path=str(ROOT/'patient-mobile.png'),full_page=True)


    def test_10_keyboard_sign_in_and_account_navigation(self):
        account=FIXTURE['users']['patient']
        email=self.page.get_by_label('Email address');email.focus();self.page.keyboard.type(account['email']);self.page.keyboard.press('Tab')
        expect(self.page.get_by_label('Password',exact=True)).to_be_focused();self.page.keyboard.type(account['password']);self.page.keyboard.press('Enter')
        expect(self.page.get_by_role('heading',name='My appointments')).to_be_visible()
        account_link=self.page.get_by_role('link',name='Account & security',exact=True);account_link.focus();account_link.press('Enter')
        expect(self.page.get_by_role('heading',name='Session & access')).to_be_visible()
    def test_11_sign_out_all_sessions_invalidates_another_browser_session(self):
        self.login();other=self.context.new_page();other.goto(URL);self.login('patient',other)
        self.page.get_by_role('link',name='Account & security',exact=True).click();self.page.get_by_role('button',name='Sign out all sessions',exact=True).click()
        expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible()
        other.get_by_role('button',name='Refresh records').click();expect(other.get_by_text('Your session ended. Sign in again.',exact=True)).to_be_visible()

if __name__=='__main__':unittest.main(verbosity=2)
