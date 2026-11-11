"""Real complete synthetic booking/assessment/inference journey; no HTTP route mocks."""
import base64,hashlib,json,struct,binascii,zlib,uuid
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import expect
from browser import BrowserFixture,ROOT,FIXTURE,URL

def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,0,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80'*64)*64))+chunk(b'IEND',b'')

class ClinicalBrowser(BrowserFixture):
    encounter=None;scan=None
    def logout(self):
        self.page.get_by_role('button',name='Sign out',exact=True).click();expect(self.page.get_by_text('You have been signed out.',exact=True)).to_be_visible()
    def clinical(self):
        self.page.get_by_role('link',name='Clinical workspace',exact=True).click()
        self.page.get_by_role('button',name='Open assessment').first.click()
        expect(self.page.get_by_role('heading',name='Assessment detail',exact=True)).to_be_visible()
        expect(self.page.get_by_text('Loading assessment…',exact=True)).to_have_count(0)
    def start(self):
        self.login();self.page.get_by_role('button',name='Book appointment',exact=True).first.click();expect(self.page.get_by_text('Appointment booked.',exact=True)).to_be_visible();self.logout();self.login('doctor')
        with self.page.expect_response(lambda r:r.url.endswith('/assessment-requests')) as response:
            self.page.get_by_role('button',name='Start assessment',exact=True).first.click()
        body=response.value.json();self.assertEqual(response.value.status,200);self.assertEqual(body['state'],'CREATED')
        self.control('assign',encounterId=body['encounterId']);return body['encounterId']
    def test_01_complete_booking_capture_real_inference_rejection_and_approval(self):
        type(self).encounter=self.start();encounter=self.encounter
        self.clinical()
        self.page.get_by_label('Internal clinical note',exact=True).fill('SYNTHETIC internal doctor note, not for the patient.')
        self.page.get_by_role('button',name='Add clinical note',exact=True).click();expect(self.page.get_by_text('Clinical action recorded.',exact=True)).to_be_visible()
        self.logout();self.login('technician');self.page.get_by_role('button',name='Open assessment').first.click()
        expect(self.page.get_by_label('Observed at (UTC)',exact=True)).to_be_visible()
        self.page.get_by_label('Observed at (UTC)',exact=True).fill(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))
        for label,value in [('Systolic BP (mmHg)','120'),('Diastolic BP (mmHg)','80'),('Pulse (bpm)','70'),('Temperature (°C)','37'),('Oxygen saturation (%)','98'),('Glucose (mg/dL)','90')]:self.page.get_by_label(label,exact=True).fill(value)
        for key in ['consciousness','questions','commands','gaze','visual','facial','leftArm','rightArm','leftLeg','rightLeg','ataxia','sensory','language','dysarthria','neglect']:self.page.get_by_label('NIHSS '+key,exact=True).fill('0')
        self.page.get_by_role('button',name='Record observations',exact=True).click();expect(self.page.get_by_text('Clinical action recorded.',exact=True)).to_be_visible()
        self.assertEqual(self.api('GET',f'/api/v1/clinical/encounters/{encounter}/predictions').status,403)
        self.page.get_by_label('PNG scan (maximum 1 MiB)',exact=True).set_input_files({'name':'malicious.png','mimeType':'image/png','buffer':b'<svg onload="alert(1)"/>'})
        self.page.get_by_role('button',name='Upload PNG',exact=True).click();expect(self.page.get_by_role('alert')).to_be_visible()
        expect(self.page.get_by_role('button',name='Run experimental inference',exact=True)).to_have_count(0)
        self.page.get_by_label('PNG scan (maximum 1 MiB)',exact=True).set_input_files({'name':'synthetic.png','mimeType':'image/png','buffer':png()})
        self.page.get_by_role('button',name='Upload PNG',exact=True).click();expect(self.page.get_by_role('button',name='Download PNG scan',exact=True)).to_be_visible()
        type(self).scan=self.api('GET',f'/api/v1/clinical/encounters/{encounter}/assessment').json()['observations']['scans'][0]['scanId']
        self.page.get_by_role('button',name='Submit assessment',exact=True).click();expect(self.page.get_by_text('SUBMITTED · revision 4',exact=True)).to_be_visible()
        self.logout();self.login('patient');self.page.get_by_role('link',name='Approved assessments',exact=True).click();expect(self.page.get_by_text('No accessible assessments yet.')).to_be_visible()
        self.assertEqual(self.api('GET',f'/api/v1/clinical/encounters/{encounter}/assessment').status,404)
        self.logout();self.login('doctor');self.clinical()
        self.page.get_by_role('button',name='Run experimental inference',exact=True).click()
        expect(self.page.get_by_text('Experimental label:',exact=False)).to_be_visible(timeout=35000)
        response=self.api('GET',f'/api/v1/clinical/encounters/{encounter}/predictions').json()['predictions'][0]
        self.assertEqual(response['state'],'SUCCEEDED');self.assertEqual(response['prediction']['scanSha256'],hashlib.sha256(png()).hexdigest())
        self.assertEqual(response['prediction']['modelSha256'],'200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595')
        print('Real synthetic inference: '+json.dumps(response['prediction'],sort_keys=True),flush=True)
        self.page.get_by_label('Experimental prediction review note',exact=True).fill('SYNTHETIC uncalibrated output acknowledged separately, not a diagnosis.')
        self.page.get_by_label('I reviewed this experimental output separately from clinical findings.',exact=True).check();self.page.get_by_role('button',name='Record prediction review',exact=True).click();expect(self.page.get_by_text('Doctor review:',exact=False)).to_be_visible()
        self.page.get_by_label('Independent clinical summary / rejection reason',exact=True).fill('SYNTHETIC request independent reassessment.')
        self.page.get_by_label('I independently reviewed these observations. This decision does not automatically approve any AI prediction.',exact=True).check();self.page.get_by_role('button',name='Reject assessment',exact=True).click();expect(self.page.get_by_text('REJECTED · revision 5',exact=True)).to_be_visible()
        self.logout();self.login('technician');self.page.get_by_role('button',name='Open assessment',exact=True).first.click();self.page.get_by_role('button',name='Submit assessment',exact=True).click();expect(self.page.get_by_text('SUBMITTED · revision 6',exact=True)).to_be_visible()
        self.logout();self.login('doctor');self.clinical();self.page.get_by_label('Independent clinical summary / rejection reason',exact=True).fill('SYNTHETIC independent clinician-approved observations. No model diagnosis or treatment is approved.')
        self.page.get_by_label('I independently reviewed these observations. This decision does not automatically approve any AI prediction.',exact=True).check();self.page.get_by_role('button',name='Approve assessment',exact=True).click();expect(self.page.get_by_text('APPROVED · revision 7',exact=True)).to_be_visible()
        self.page.screenshot(path=str(ROOT/'clinical-doctor.png'),full_page=True)
        self.logout();self.login('patient');self.page.get_by_role('link',name='Approved assessments',exact=True).click();self.page.get_by_role('button',name='Open assessment',exact=True).click()
        expect(self.page.get_by_role('heading',name='Clinician-approved summary',exact=True)).to_be_visible();expect(self.page.get_by_text('Experimental AI predictions',exact=True)).to_have_count(0);expect(self.page.get_by_text('SYNTHETIC internal doctor note, not for the patient.',exact=True)).to_have_count(0)
        with self.page.expect_download() as download:self.page.get_by_role('button',name='Download PNG scan',exact=True).click()
        self.assertEqual(Path(download.value.path()).read_bytes(),png())
        self.page.set_viewport_size({'width':390,'height':844});self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),390);self.page.screenshot(path=str(ROOT/'clinical-patient-mobile.png'),full_page=True)
        body=self.api('GET',f'/api/v1/clinical/encounters/{encounter}/assessment').json();self.assertNotIn('history',body);self.assertNotIn('notes',body['observations']);self.assertEqual(self.api('GET',f'/api/v1/clinical/encounters/{encounter}/predictions').status,403)
    def test_02_cross_patient_admin_and_technician_restrictions(self):
        self.assertIsNotNone(self.encounter);self.login('otherPatient');self.page.get_by_role('link',name='Approved assessments',exact=True).click();expect(self.page.get_by_text('No accessible assessments yet.')).to_be_visible()
        for suffix in ['assessment','scans/'+self.scan]:self.assertEqual(self.api('GET',f'/api/v1/clinical/encounters/{self.encounter}/'+suffix).status,404)
        self.logout();self.login('technician');self.assertEqual(self.api('GET',f'/api/v1/clinical/encounters/{self.encounter}/predictions').status,403)
        self.logout();self.login('admin');self.assertEqual(self.api('GET','/api/v1/clinical/workspace').status,403)
        self.page.evaluate("history.pushState(null,'','/clinical');dispatchEvent(new PopStateEvent('popstate'))");expect(self.page.get_by_text('This workspace is not available to your account.',exact=True)).to_be_visible()
    def test_03_clinical_outage_retry_uses_same_idempotency_command(self):
        encounter=self.start();self.clinical();commands=[]
        self.page.on('request',lambda r:commands.append(r.post_data_json) if r.method=='POST' and r.url.endswith('/assessment') else None)
        self.control('pauseClinical')
        try:
            self.page.get_by_label('Internal clinical note',exact=True).fill('SYNTHETIC note after transport recovery')
            self.page.get_by_role('button',name='Add clinical note',exact=True).click();expect(self.page.get_by_role('button',name='Retry pending action',exact=True)).to_be_visible();expect(self.page.get_by_role('alert')).to_be_visible()
        finally:self.control('resumeClinical')
        self.page.get_by_role('button',name='Retry pending action',exact=True).click();expect(self.page.get_by_text('Clinical action recorded.',exact=True)).to_be_visible()
        self.assertEqual(commands[0],commands[1]);body=self.api('GET',f'/api/v1/clinical/encounters/{encounter}/assessment').json();self.assertEqual(len(body['observations']['notes']),1)
    def test_04_staff_activation_role_change_and_revocation(self):
        self.login('admin');name='Synthetic invited '+uuid.uuid4().hex[:6];email=uuid.uuid4().hex+'@example.test';password='Synthetic-'+uuid.uuid4().hex
        self.page.get_by_label('Staff name',exact=True).fill(name);self.page.get_by_label('Staff email',exact=True).fill(email);self.page.get_by_label('Staff role',exact=True).select_option('technician');self.page.get_by_label('Your current password',exact=True).fill(FIXTURE['users']['admin']['password']);self.page.get_by_label('Authorization reason',exact=True).fill('SYNTHETIC independent staff onboarding approval');self.page.get_by_role('button',name='Invite staff member',exact=True).click()
        notice=self.page.get_by_role('status');expect(notice).to_contain_text('Delivery ID:');import re
        delivery=re.search(r'Delivery ID: ([a-f0-9-]{36})',notice.inner_text()).group(1)
        self.control('deliver',deliveryId=delivery,verified='HANDOFF',operator='synthetic-browser-operator');payload=json.loads((ROOT/'delivery-once.json').read_text());(ROOT/'delivery-once.json').unlink();self.assertEqual(payload['email'],email)
        self.logout();self.page.get_by_role('link',name='Recover or activate an account',exact=True).click();self.page.get_by_label('Private activation or recovery token',exact=True).fill(payload['token']);self.page.get_by_label('New password',exact=True).fill(password);self.page.get_by_role('button',name='Set new password',exact=True).click();expect(self.page.get_by_text('Password updated. Sign in again.',exact=True)).to_be_visible()
        self.page.get_by_role('link',name='Return to sign in',exact=True).click();self.page.get_by_label('Email address').fill(email);self.page.get_by_label('Password',exact=True).fill(password);self.page.get_by_role('button',name='Sign in',exact=True).click();expect(self.page.get_by_role('heading',name='Assigned assessment workspace',exact=True)).to_be_visible();old=self.token;self.assertEqual(self.api('GET','/api/v1/clinical/workspace').status,403);self.assertEqual(self.api('GET','/api/v1/identity/me',old).status,200);self.page.reload();expect(self.page.get_by_role('button',name='Sign in',exact=True)).to_be_visible()
        self.login('admin');self.page.get_by_role('button',name='Manage '+name,exact=True).click();self.page.get_by_label('New staff role',exact=True).select_option('doctor');self.page.get_by_label('Confirm your current password',exact=True).fill(FIXTURE['users']['admin']['password']);self.page.get_by_label('Change authorization reason',exact=True).fill('SYNTHETIC approved role change');self.page.get_by_label('I am authorized to make this security change.',exact=True).check();self.page.get_by_role('button',name='Apply staff security change',exact=True).click();expect(self.page.get_by_role('status')).to_contain_text('Staff security change recorded');self.assertEqual(self.api('GET','/api/v1/identity/me',old).status,401)
        staff_page=self.context.new_page();staff_tokens=[]
        staff_page.on('response',lambda r:staff_tokens.append(r.json()['token']) if r.url.endswith('/auth/login') and r.status==200 else None)
        staff_page.goto(URL);staff_page.get_by_label('Email address').fill(email);staff_page.get_by_label('Password',exact=True).fill(password);staff_page.get_by_role('button',name='Sign in',exact=True).click();expect(staff_page.get_by_role('heading',name='Assigned appointments',exact=True)).to_be_visible()
        self.assertEqual(self.api('GET','/api/v1/identity/me',staff_tokens[-1]).status,200)
        self.page.get_by_role('button',name='Manage '+name,exact=True).click();self.page.get_by_label('Security operation',exact=True).select_option('revoke');self.page.get_by_label('Confirm your current password',exact=True).fill(FIXTURE['users']['admin']['password']);self.page.get_by_label('Change authorization reason',exact=True).fill('SYNTHETIC approved offboarding');self.page.get_by_label('I am authorized to make this security change.',exact=True).check();self.page.get_by_role('button',name='Apply staff security change',exact=True).click();expect(self.page.get_by_role('status')).to_contain_text('Staff security change recorded');self.assertEqual(self.api('GET','/api/v1/identity/me',staff_tokens[-1]).status,401);self.logout()
        self.page.get_by_label('Email address').fill(email);self.page.get_by_label('Password',exact=True).fill(password);self.page.get_by_role('button',name='Sign in',exact=True).click();expect(self.page.get_by_role('alert')).to_contain_text('Email or password not accepted')
        self.page.get_by_role('link',name='Recover or activate an account',exact=True).click();self.page.get_by_label('Registered email',exact=True).fill(email);self.page.get_by_role('button',name='Request recovery instructions',exact=True).click();expect(self.page.get_by_text('If recovery is available, instructions will be delivered through the registered channel.',exact=True)).to_be_visible()

if __name__=='__main__':import unittest;unittest.main(verbosity=2)
