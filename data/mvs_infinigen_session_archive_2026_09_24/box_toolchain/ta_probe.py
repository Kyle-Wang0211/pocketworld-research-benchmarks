import tartanair as ta, time
ta.init("/root/ta_raw")
t=time.time()
ta.download(env=["AmericanDiner"], difficulty=["easy"], modality=["image","depth"], camera_name=["lcam_front"], unzip=True, delete_zip=True, num_workers=8, data_source="huggingface")
print("DONE %.0fs" % (time.time()-t), flush=True)
